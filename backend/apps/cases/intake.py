"""Dépôt groupé (DEP-01 à DEP-06) : des pièces déposées ensemble, réparties en dossiers proposés.

Chaque pièce est contrôlée par l'antivirus, puis lue comme au dépôt dans un dossier : type d'après
le titre, puis les informations utiles de sa lecture (facture, titre de transport, assurance).

Les pièces sont regroupées uniquement sur des références imprimées qu'elles partagent : le numéro
de facture (porté par la facture, cité par le B/L ou l'assurance), le numéro de B/L et le numéro
de conteneur. Le nom de l'importateur ne regroupe jamais à lui seul : une même société peut avoir
plusieurs envois, donc plusieurs dossiers. Deux noms différents dans un même groupe sont signalés.
Une pièce sans référence lue reste « à classer », jamais rattachée au hasard.

Rien n'est créé avant la confirmation de l'agent, qui peut déplacer une pièce d'un dossier à un
autre. La confirmation crée les dossiers, y rattache les pièces et demande leur lecture complète.
"""

import logging
import re
import unicodedata

from django.db import transaction

from apps.core.exceptions import ApiError
from apps.documents import services as documents
from apps.documents.models import Document
from apps.documents.sniff import Readability
from apps.documents.storage import get_storage
from apps.extraction import adapters
from apps.extraction import services as extraction
from apps.extraction.detection import detect_document_type
from apps.extraction.readers import INSURANCE, INVOICE, READER_FOR_TYPE, TRANSPORT
from apps.extraction.schema import Status

from . import services

logger = logging.getLogger(__name__)

MAX_DOCUMENTS = 200
NOT_FOUND = ("NOT_FOUND", "Pièce introuvable.", 404)

# Références de chaque lecture : (champ lu, nature de la référence, portée par la pièce ou citée).
REFERENCES = {
    INVOICE: (("invoice_number", "invoice", "own"), ("related_bl", "bl", "cited"), ("container", "container", "cited")),
    TRANSPORT: (
        ("transport_number", "bl", "own"),
        ("related_invoice", "invoice", "cited"),
        ("container", "container", "cited"),
    ),
    INSURANCE: (
        ("related_invoice", "invoice", "cited"),
        ("related_bl", "bl", "cited"),
        ("container", "container", "cited"),
    ),
}
PARTY = {INVOICE: "buyer_name", TRANSPORT: "consignee", INSURANCE: "insured"}
KIND_LABELS = {"invoice": "Facture", "bl": "Titre de transport", "container": "Conteneur"}


def _key(value: str) -> str:
    """Référence comparable : « MSCU 771205-4 » et « MSCU7712054 » sont la même."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _party_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _reading(document: Document, reader: str):
    path = get_storage().path_for_reading(document.object_key)
    return adapters.run(document.mime, path, ocr=False, progress=lambda *_: None, reader=reader)


def analyze(document: Document) -> dict:
    """Type, partie (acheteur, destinataire ou assuré) et références lues sur une pièce."""
    out = {
        "document_id": str(document.id),
        "name": document.original_name,
        "type": "",
        "party": "",
        "references": [],
        "read": False,
    }
    detection = detect_document_type(document) or {}
    out["type"] = detection.get("code", "")
    reader = READER_FOR_TYPE.get(out["type"])
    if reader not in REFERENCES or document.readability != Readability.OK:
        return out
    try:
        parsed = _reading(document, reader)
    except Exception:  # une pièce illisible reste à classer ; elle ne bloque jamais le dépôt
        logger.info("Intake reading skipped for document %s", document.id, exc_info=True)
        return out
    out["read"] = True
    header = {name: v for name, v in parsed.header.items() if v.status == Status.OK and v.raw}
    if party := header.get(PARTY[reader]):
        out["party"] = str(party.raw).strip()
    for field, kind, role in REFERENCES[reader]:
        if (value := header.get(field)) and _key(str(value.raw)):
            out["references"].append({"kind": kind, "value": str(value.raw).strip(), "role": role})
    return out


def upload(*, org, actor, upload, declared_mime="") -> tuple[Document, list[str]]:
    """Dépôt d'une pièce sans dossier. Un fichier identique déjà présent est réutilisé, pas doublé."""

    class _Duplicate(Exception):
        pass

    try:
        with transaction.atomic():
            document = documents.store_upload(organization=org, actor=actor, upload=upload, declared_mime=declared_mime)
            duplicates = documents.find_duplicates(org, document.sha256, exclude_id=document.id)
            if duplicates:
                documents.get_storage().discard(document.object_key)
                raise _Duplicate(duplicates[0])
    except _Duplicate as dup:
        document = dup.args[0]
    cases = sorted({link.revision.case.reference for link in document.case_links.select_related("revision__case")})
    return document, cases


def _documents(org, ids) -> list[Document]:
    if not isinstance(ids, list) or not ids or len(ids) > MAX_DOCUMENTS:
        raise ApiError("VALIDATION_ERROR", f"Indiquer de 1 à {MAX_DOCUMENTS} pièces.", 400)
    ids = [str(i) for i in ids]
    if len(set(ids)) != len(ids):
        raise ApiError("VALIDATION_ERROR", "Une pièce ne peut figurer qu'une fois.", 400)
    try:
        found = {str(d.id): d for d in Document.objects.for_organization(org).filter(pk__in=ids)}
    except Exception:
        raise ApiError(*NOT_FOUND) from None
    if len(found) != len(ids):
        raise ApiError(*NOT_FOUND)
    return [found[i] for i in ids]


def propose(*, org, document_ids) -> dict:
    """Groupes proposés : les pièces liées par une référence partagée forment un dossier."""
    analyses = [analyze(d) for d in _documents(org, document_ids)]
    parent = list(range(len(analyses)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    holders: dict[tuple[str, str], list[int]] = {}
    for i, a in enumerate(analyses):
        for ref in a["references"]:
            holders.setdefault((ref["kind"], _key(ref["value"])), []).append(i)
    for members in holders.values():
        for j in members[1:]:
            parent[find(j)] = find(members[0])

    groups: dict[int, list[int]] = {}
    for i in range(len(analyses)):
        groups.setdefault(find(i), []).append(i)

    proposals, unassigned = [], []
    for members in groups.values():
        pieces = [analyses[i] for i in members]
        if len(members) == 1 and not pieces[0]["references"]:
            unassigned.append({**pieces[0], "why": "Aucune référence lue : à classer par l'agent."})
            continue
        reasons = []
        for (kind, _), holders_of in holders.items():
            shared = [i for i in holders_of if i in members]
            if len(shared) > 1:
                value = next(r["value"] for r in analyses[shared[0]]["references"] if r["kind"] == kind)
                reasons.append({"kind": kind, "value": value, "documents": len(shared)})
        parties: dict[str, str] = {}
        for p in pieces:
            if p["party"]:
                parties.setdefault(_party_key(p["party"]), p["party"])
        warnings = []
        if len(parties) > 1:
            warnings.append("Noms différents sur les pièces : " + " ; ".join(parties.values()) + ". À vérifier.")
        proposals.append(
            {
                "title": next(iter(parties.values()), "") or pieces[0]["name"],
                "party": next(iter(parties.values()), ""),
                "parties": list(parties.values()),
                "documents": pieces,
                "reasons": reasons,
                "warnings": warnings,
            }
        )
    proposals.sort(key=lambda g: g["title"].lower())
    return {"groups": proposals, "unassigned": unassigned}


def create_cases(*, org, actor, groups) -> list[dict]:
    """Crée un dossier par groupe confirmé, y rattache ses pièces et demande leur lecture."""
    if not isinstance(groups, list) or not groups or len(groups) > MAX_DOCUMENTS:
        raise ApiError("VALIDATION_ERROR", "Indiquer au moins un dossier à créer.", 400)
    all_ids = []
    for g in groups:
        if not isinstance(g, dict) or not isinstance(g.get("document_ids"), list) or not g["document_ids"]:
            raise ApiError("VALIDATION_ERROR", "Chaque dossier doit contenir au moins une pièce.", 400)
        all_ids += [str(i) for i in g["document_ids"]]
    docs = {str(d.id): d for d in _documents(org, all_ids)}
    created, links = [], []
    with transaction.atomic():
        for g in groups:
            title = str(g.get("title") or "").strip()[:200]
            case = services.create_case(org=org, actor=actor, data={"title": title})
            revision = case.current_revision
            for doc_id in g["document_ids"]:
                link = services._link_document(org, actor, revision, docs[str(doc_id)], services.AUTO)
                links.append(link)
            services._event(
                org,
                actor,
                "case.created_from_intake",
                case,
                case,
                current={"documents": [str(i) for i in g["document_ids"]], "title": title},
            )
            created.append({"id": str(case.id), "reference": case.reference, "title": title,
                            "documents": len(g["document_ids"])})  # fmt: skip
        for link in links:
            try:
                extraction.request_extraction(org=org, actor=actor, link_id=link.id)
            except ApiError:
                pass  # pièce sans lecture automatique : elle reste jointe, l'agent la traite à la main
    return created
