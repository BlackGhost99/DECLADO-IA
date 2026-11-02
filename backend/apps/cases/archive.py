"""Archive complète du dossier (EXP-04, T84) : un seul fichier ZIP pour conserver ou transmettre.

L'archive réunit, pour chaque révision : les pièces originales (octets conservés après
l'antivirus, jamais retouchés), les exports conservés (projet DAU, récapitulatif PDF, détail
Excel), le circuit de validation et les décisions de code ; pour le dossier : le journal
d'audit complet et un manifeste avec l'empreinte SHA-256 de chaque fichier.

Le projet DAU et le détail Excel de la révision courante sont générés s'il n'en existe pas
pour son calcul actuel : ils sont alors conservés et journalisés comme tout export. Une
révision validée l'est en interne, jamais acceptée par la Douane ; l'archive le rappelle.
"""

import csv
import hashlib
import io
import json
import re
import tempfile
import zipfile

from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.documents.storage import get_storage

from . import exports, services
from .models import CaseExport, CaseRevision, ClassificationDecision

# Libellés de sortie regroupés ici, comme ceux des exports : une autre langue s'ajoutera sans toucher au contenu.
TEXT = {
    "readme_title": "Dossier {ref} : archive complète",
    "readme_generated": "Archive générée le {date} par {actor} pour {org}.",
    "readme_state_validated": (
        "Révision courante {no} : validée en interne. Ce n'est pas une acceptation par la Douane."
    ),
    "readme_state_draft": (
        "Révision courante {no} : {state}, non validée en interne. Ne pas transmettre comme dossier définitif."
    ),
    "readme_demo": "Contient des données fictives de démonstration.",
    "readme_content": (
        "Contenu :\n"
        "- revision-N/pieces/ : pièces originales telles que déposées (après antivirus) ;\n"
        "- revision-N/pieces-remplacees/ : pièces remplacées, gardées pour la traçabilité ;\n"
        "- revision-N/exports/ : projets DAU, récapitulatifs PDF et détails Excel conservés ;\n"
        "- revision-N/circuit-validation.csv : soumissions, retours et validations internes ;\n"
        "- revision-N/decisions-codes.csv : codes confirmés, complétés, remplacés ou classés ;\n"
        "- revision-N/calcul-valide.json : calcul figé à la validation interne, s'il y en a une ;\n"
        "- journal.csv : historique complet du dossier ;\n"
        "- manifeste.json : liste des fichiers avec leur empreinte SHA-256."
    ),
    "readme_altered": "ATTENTION : empreinte différente de celle enregistrée au dépôt pour : {files}.",
    "journal_header": ["date", "action", "type", "identifiant", "auteur", "avant", "après"],
    "circuit_header": ["date", "étape", "auteur", "motif", "empreinte du calcul"],
    "decisions_header": [
        "marchandise",
        "désignation",
        "date",
        "action",
        "code retenu",
        "édition",
        "auteur",
        "motif",
        "à jour",
    ],  # fmt: skip
    "yes": "oui",
    "no": "non (données modifiées depuis)",
    "system": "système",
}

_UNSAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)


def _safe_name(name: str, fallback: str) -> str:
    """Nom de fichier sans chemin ni caractère réservé (pas de « .. » ni de « / » dans l'archive)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _UNSAFE.sub("_", base).strip(" .")
    return base[:150] or fallback


def _unique(name: str, taken: set[str]) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    candidate, n = name, 2
    while candidate.lower() in taken:
        candidate = f"{stem}_{n}{'.' + ext if ext else ''}"
        n += 1
    taken.add(candidate.lower())
    return candidate


def _cell(value) -> str:
    """Cellule CSV : une valeur commençant par =, +, - ou @ reste un texte dans un tableur."""
    text = "" if value is None else str(value)
    if text.startswith(exports.FORMULA_PREFIXES):
        text = "'" + text
    return text


def _csv(header: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _who(user) -> str:
    return (user.full_name or user.email) if user else TEXT["system"]


def _ensure_current_exports(org, actor, case) -> None:
    """Projet DAU et détail Excel de la révision courante, pour son calcul actuel."""
    revision = case.current_revision
    _, fingerprint, validated = exports._calculation(case, revision)
    marking = CaseExport.Marking.VALIDATED if validated else CaseExport.Marking.DRAFT
    present = set(
        revision.exports.filter(calculation_fingerprint=fingerprint, marking=marking).values_list("format", flat=True)
    )
    for fmt in (CaseExport.Format.PDF, CaseExport.Format.XLSX):
        if fmt not in present:
            exports.create_export(org=org, actor=actor, case_id=case.id, fmt=fmt)


class _Writer:
    def __init__(self, archive: zipfile.ZipFile):
        self.archive = archive
        self.files: list[dict] = []
        self.altered: list[str] = []

    def add(self, path: str, content: bytes, **meta):
        self.archive.writestr(path, content)
        self.files.append({"path": path, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content), **meta})

    def add_stored(self, path: str, key: str, recorded_sha256: str, **meta):
        """Copie en flux un fichier du stockage privé et vérifie son empreinte d'origine."""
        digest, size = hashlib.sha256(), 0
        with get_storage().open(key) as src, self.archive.open(path, "w", force_zip64=True) as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                dst.write(chunk)
        sha = digest.hexdigest()
        intact = sha == recorded_sha256
        if not intact:
            self.altered.append(path)
        self.files.append({"path": path, "sha256": sha, "bytes": size, "intact": intact, **meta})


def _revision_files(w: _Writer, revision: CaseRevision) -> dict:
    folder = f"revision-{revision.revision_no}"
    taken: set[str] = set()
    links = revision.documents.select_related("document").order_by("created_at")
    for link in links:
        doc = link.document
        sub = "pieces-remplacees" if link.replaced_by_id else "pieces"
        name = _unique(_safe_name(doc.original_name, f"piece-{doc.id}"), taken)
        w.add_stored(
            f"{folder}/{sub}/{name}",
            doc.object_key,
            doc.sha256,
            source="piece",
            usage=link.get_usage_display(),
            document_id=str(doc.id),
        )
    for e in revision.exports.select_related("created_by").order_by("created_at"):
        name = _unique(_safe_name(e.filename, f"export-{e.id}"), taken)
        w.add_stored(
            f"{folder}/exports/{name}",
            e.object_key,
            e.sha256,
            source="export",
            format=e.format,
            marking=e.marking,
            created_at=e.created_at.isoformat(),
            calculation_fingerprint=e.calculation_fingerprint,
        )
    decisions = list(revision.decisions.select_related("actor"))
    w.add(
        f"{folder}/circuit-validation.csv",
        _csv(
            TEXT["circuit_header"],
            [
                [d.created_at.isoformat(), d.get_kind_display(), _who(d.actor), d.reason, d.fingerprint]
                for d in decisions
            ],
        ),
        source="circuit",
    )
    rows = []
    for goods in revision.goods_lines.order_by("ordinal"):
        latest = None
        for d in ClassificationDecision.objects.filter(goods_line=goods).select_related("actor", "edition"):
            if latest is None:
                latest = d
                current = TEXT["yes"] if services.decision_is_current(d, goods) else TEXT["no"]
            else:
                current = ""
            rows.append(
                [
                    goods.ordinal,
                    goods.description,
                    d.created_at.isoformat(),
                    d.get_action_display(),
                    exports._code(d.selected_code),
                    str(d.edition),
                    _who(d.actor),
                    d.reason,
                    current,
                ]
            )
    w.add(f"{folder}/decisions-codes.csv", _csv(TEXT["decisions_header"], rows), source="decisions")
    validated = next((d for d in reversed(decisions) if d.kind == d.Kind.VALIDATED), None)
    if validated is not None:
        w.add(
            f"{folder}/calcul-valide.json",
            json.dumps(
                {
                    "fingerprint": validated.fingerprint,
                    "validated_at": validated.created_at.isoformat(),
                    "snapshot": validated.snapshot,
                },  # fmt: skip
                ensure_ascii=False,
                indent=2,
                default=str,
            ).encode("utf-8"),
            source="calcul",
        )
    return {
        "revision_no": revision.revision_no,
        "state": revision.state,
        "state_label": revision.get_state_display(),
        "mode": revision.mode,
        "reason": revision.reason,
        "created_at": revision.created_at.isoformat(),
    }


def build_archive(*, org, actor, case_id) -> tuple[str, tempfile.SpooledTemporaryFile]:
    """Construit l'archive du dossier ; la requête est atomique, le fichier reste en mémoire ou sur disque."""
    case = services.lock_case(org, case_id)
    _ensure_current_exports(org, actor, case)
    case.refresh_from_db()
    current = case.current_revision
    validated = current.state in (CaseRevision.State.VALIDATED, CaseRevision.State.ARCHIVED)
    now = timezone.now()

    spool = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        w = _Writer(archive)
        revisions = [
            _revision_files(w, r)
            for r in CaseRevision.objects.for_organization(org).filter(case=case).order_by("revision_no")
        ]
        events = AuditEvent.objects.filter(organization=org, scope=case.scope).select_related("actor").order_by("at")
        w.add(
            "journal.csv",
            _csv(
                TEXT["journal_header"],
                [
                    [
                        e.at.isoformat(),
                        _event_label(e.event_type),
                        e.event_type,
                        e.entity_id,
                        _who(e.actor),
                        json.dumps(e.previous, ensure_ascii=False, default=str) if e.previous else "",
                        json.dumps(e.current, ensure_ascii=False, default=str) if e.current else "",
                    ]  # fmt: skip
                    for e in events
                ],
            ),
            source="journal",
        )
        readme = [
            TEXT["readme_title"].format(ref=case.reference),
            "",
            TEXT["readme_generated"].format(date=exports._when(now), actor=_who(actor), org=org.name),
            (
                TEXT["readme_state_validated"].format(no=current.revision_no)
                if validated
                else TEXT["readme_state_draft"].format(no=current.revision_no, state=current.get_state_display())
            ),
        ]
        if any(r["mode"] == CaseRevision.Mode.DEMO for r in revisions):
            readme.append(TEXT["readme_demo"])
        if w.altered:
            readme.append(TEXT["readme_altered"].format(files=", ".join(w.altered)))
        readme += ["", TEXT["readme_content"], ""]
        manifest = {
            "case": {
                "id": str(case.id),
                "reference": case.reference,
                "title": case.title,
                "importer": case.importer.name if case.importer else None,
            },  # fmt: skip
            "organization": org.name,
            "generated_at": now.isoformat(),
            "generated_by": _who(actor),
            "current_revision": current.revision_no,
            "internal_validation_only": True,
            "revisions": revisions,
            "files": w.files,
            "altered": w.altered,
        }
        archive.writestr("LISEZMOI.txt", "\n".join(readme).encode("utf-8"))
        archive.writestr("manifeste.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

    size = spool.tell()
    spool.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: spool.read(1024 * 1024), b""):
        digest.update(chunk)
    spool.seek(0)
    services._event(
        org,
        actor,
        "case.archive_downloaded",
        case,
        case,
        None,
        {
            "revision": current.revision_no,
            "files": len(w.files),
            "bytes": size,
            "sha256": digest.hexdigest(),
            "altered": w.altered,
        },  # fmt: skip
    )
    filename = f"{case.reference}_dossier_complet{'' if validated else '_brouillon'}.zip"
    return filename, spool


def _event_label(event_type: str) -> str:
    """Libellé lisible d'un événement : le type technique reste dans la colonne suivante."""
    return EVENT_LABELS.get(event_type, event_type)


EVENT_LABELS = {
    "case.created": "Dossier créé",
    "case.updated": "Dossier modifié",
    "case.assigned": "Dossier attribué",
    "case.archive_downloaded": "Archive complète téléchargée",
    "revision.created": "Nouvelle révision",
    "revision.updated": "Révision modifiée",
    "revision.submitted": "Soumis pour validation",
    "revision.returned": "Retourné pour correction",
    "revision.validated": "Validé en interne",
    "revision.exported": "Export généré",
    "case.document_attached": "Pièce ajoutée",
    "case.document_replaced": "Pièce remplacée",
    "invoice.created": "Facture ajoutée",
    "invoice.extracted": "Facture lue",
    "invoice.field_confirmed": "Champ de facture confirmé",
    "goods_line.created": "Marchandise ajoutée",
    "goods_line.code_checked": "Code contrôlé",
    "goods_line.code_decided": "Décision sur le code",
    "goods_line.codes_confirmed": "Codes confirmés en une fois",
}
