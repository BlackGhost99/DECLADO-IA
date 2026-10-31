"""DOS-02 : un brouillon peut être incomplet, mais ses manques sont listés, ligne par ligne.

« blocking » : nécessaire avant calcul ou validation. « warnings » : à examiner, sans blocage.
Les écarts arithmétiques sont signalés, jamais corrigés (EXT-05, EXT-06).
"""

import re
from decimal import Decimal

from apps.document_graph.models import DocumentConflict
from apps.extraction import services as extraction
from apps.tariffs.models import PublicationState

from . import services
from .models import CaseDocument, CaseRevision

FIELD_LABELS = {
    "supplier_name": "fournisseur",
    "invoice_number": "n° de facture",
    "invoice_date": "date",
    "currency": "devise",
    "incoterm": "incoterm",
    "declared_total": "total imprimé",
    "source_reference": "réf. fournisseur",
    "description_raw": "désignation",
    "quantity": "quantité",
    "unit": "unité",
    "unit_price": "prix unitaire",
    "amount": "montant",
    "origin_country": "origine",
    "code:customs": "code douanier",
    "code:supplier": "référence fournisseur",
    "code:ambiguous": "code de nature incertaine",
}


def _fmt(value) -> str:
    return "?" if value is None else format(Decimal(value).normalize(), "f")


def _item(scope, obj, field, message, label=""):
    return {"scope": scope, "id": str(obj.id), "label": label, "field": field, "message": message}


PREFILLED_LABELS = {
    "target_edition": "édition du référentiel",
    "planned_declaration_date": "date de déclaration prévue",
    "regime": "régime (repris du dernier dossier)",
    "importer": "importateur (reconnu d'après l'acheteur de la facture)",
}


# Champs de ligne dont l'absence ne mérite aucun signalement, et ceux déjà bloquants s'ils manquent.
OPTIONAL_LINE_FIELDS = {"source_reference"}
BLOCKING_LINE_FIELDS = {"description_raw", "quantity", "unit", "amount"}


def _to_check(field: str, message: str) -> str:
    """« À vérifier (fournisseur) : Émetteur lu en tête de la facture. » : le champ est nommé, une seule fois."""
    name = FIELD_LABELS.get(field, field)
    message = re.sub(r"\s*:\s*à vérifier\.?$", ".", message.strip(), flags=re.IGNORECASE)
    return f"À vérifier ({name}) : {message}" if name else f"À vérifier : {message}"


def _origin_covered(line, revision) -> bool:
    """Ligne rattachée : l'origine se signale une seule fois, sur la marchandise."""
    return bool(line.goods_sources.all()) or bool(revision.origin_country)


def evaluate(revision: CaseRevision) -> dict:
    blocking, warnings = [], []
    case = revision.case
    if case.importer_id is None:
        buyers = sorted({inv.buyer_name for inv in revision.invoices.all() if inv.buyer_name})
        message = "Importateur à renseigner."
        if buyers:
            message = f"Importateur à renseigner (acheteur lu sur la facture : {', '.join(buyers)})."
        blocking.append(_item("case", case, "importer", message, case.reference))
    for field, message in (
        ("planned_declaration_date", "Date de déclaration prévue à renseigner."),
        ("regime", "Régime douanier à renseigner."),
        ("target_edition", "Édition du référentiel à choisir."),
    ):
        if not getattr(revision, field if field != "target_edition" else "target_edition_id"):
            blocking.append(_item("revision", revision, field, message, f"Révision {revision.revision_no}"))
    if revision.prefilled:
        names = ", ".join(PREFILLED_LABELS.get(f, f) for f in revision.prefilled)
        warnings.append(
            _item(
                "revision",
                revision,
                "prefilled",
                f"Proposé automatiquement, à confirmer : {names}.",
                f"Révision {revision.revision_no}",
            )
        )
    if revision.target_edition_id and revision.target_edition.publication_state != PublicationState.OPERATIONAL:
        warnings.append(
            _item(
                "revision",
                revision,
                "target_edition",
                "Édition de consultation historique : aucun calcul opérationnel possible avec elle.",
                revision.target_edition.label,
            )
        )
    live_docs = revision.documents.filter(replaced_by__isnull=True)
    if not live_docs.filter(usage=CaseDocument.Usage.INVOICE).exists():
        warnings.append(_item("revision", revision, "documents", "Aucune facture jointe comme pièce.", "Pièces"))
    for link in live_docs.select_related("document").exclude(document__readability="ok"):
        warnings.append(
            _item("document", link, "readability", link.document.get_readability_display(), link.document.original_name)
        )

    invoices = list(revision.invoices.prefetch_related("lines__goods_sources").all())
    if not invoices:
        blocking.append(
            _item("revision", revision, "invoices", "Aucune facture saisie.", f"Révision {revision.revision_no}")
        )
    for inv in invoices:
        label = f"Facture {inv.ordinal}" + (f" ({inv.invoice_number})" if inv.invoice_number else "")
        for field, message in (
            ("supplier_name", "Fournisseur à renseigner."),
            ("invoice_number", "Numéro de facture à renseigner."),
            ("invoice_date", "Date de facture à renseigner."),
            ("currency", "Devise à renseigner."),
        ):
            if not getattr(inv, field):
                blocking.append(_item("invoice", inv, field, message, label))
        lines = list(inv.lines.all())
        if not lines:
            blocking.append(_item("invoice", inv, "lines", "Aucune ligne facturée.", label))
        if inv.declared_total is None:
            warnings.append(
                _item(
                    "invoice", inv, "declared_total", "Total imprimé non saisi : contrôle de somme impossible.", label
                )
            )
        elif lines and all(ln.amount is not None for ln in lines):
            totals = extraction.invoice_totals(inv)
            if totals["status"] == "gap":
                c = totals["components"]
                has_charges = any(Decimal(c[k]) for k in ("fees", "discounts", "taxes"))
                detail = (
                    f"Total recalculé {_fmt(totals['computed_total'])} (marchandises {_fmt(c['goods'])}"
                    f" + frais {_fmt(c['fees'])} − remises {_fmt(c['discounts'])} + taxes {_fmt(c['taxes'])})"
                    if has_charges
                    else f"Somme des lignes {_fmt(c['goods'])}"
                )
                warnings.append(
                    _item(
                        "invoice",
                        inv,
                        "declared_total",
                        f"{detail} ≠ total imprimé {_fmt(totals['printed_total'])} (écart {_fmt(totals['gap'])}) : "
                        "remise, frais ou erreur à expliquer.",
                        label,
                    )
                )
        for flag in inv.review_flags:
            field = flag.get("field", "")
            warnings.append(_item("invoice", inv, field, _to_check(field, flag["message"]), label))
        for divergence in inv.divergences.filter(state="open").select_related("invoice_line"):
            where = f"{label}, ligne {divergence.invoice_line.ordinal}" if divergence.invoice_line_id else label
            field = FIELD_LABELS.get(divergence.field_name, divergence.field_name)
            message = (
                "Ligne absente de la dernière lecture : la conserver ou la corriger."
                if divergence.kind == "line_not_reread"
                else f"La relecture contredit la valeur actuelle ({field}) : trancher."
            )
            blocking.append(_item("divergence", divergence, divergence.field_name or "line", message, where))
        for ln in lines:
            line_label = f"{label}, ligne {ln.ordinal}"
            for field, message in (
                ("description_raw", "Désignation à renseigner."),
                ("quantity", "Quantité inconnue."),
                ("unit", "Unité à renseigner."),
                ("amount", "Montant inconnu."),
                ("origin_country", "Origine à renseigner."),
            ):
                if getattr(ln, field) in (None, ""):
                    if field == "origin_country" and _origin_covered(ln, revision):
                        continue
                    blocking.append(_item("invoice_line", ln, field, message, line_label))
            if ln.amount is not None and ln.amount < 0:
                warnings.append(
                    _item(
                        "invoice_line",
                        ln,
                        "amount",
                        "Montant négatif : avoir ou retour à traiter explicitement.",
                        line_label,
                    )
                )
            if None not in (ln.quantity, ln.unit_price, ln.amount) and ln.quantity * ln.unit_price != ln.amount:
                warnings.append(
                    _item(
                        "invoice_line",
                        ln,
                        "amount",
                        f"Quantité × prix unitaire = {format((ln.quantity * ln.unit_price).normalize(), 'f')}, "
                        f"montant lu {format(ln.amount.normalize(), 'f')}.",
                        line_label,
                    )
                )
            for flag in ln.review_flags:
                field = flag.get("field", "")
                if str(flag.get("code", "")).startswith("CODE_") or field.startswith("code:"):
                    continue  # déjà couvert par le contrôle de code de la marchandise
                if flag.get("code") == "MISSING" and field in OPTIONAL_LINE_FIELDS:
                    continue  # facultatif : son absence n'est pas une anomalie
                if flag.get("code") == "MISSING" and field == "origin_country" and _origin_covered(ln, revision):
                    continue
                if flag.get("code") == "MISSING" and field in BLOCKING_LINE_FIELDS:
                    continue  # déjà signalé comme bloquant ci-dessus
                warnings.append(_item("invoice_line", ln, field, _to_check(field, flag["message"]), line_label))
            if not ln.goods_sources.all():
                warnings.append(
                    _item("invoice_line", ln, "goods_line", "Ligne non rattachée à une marchandise.", line_label)
                )

    # Une contradiction explicite ne peut être ignorée lors de la validation interne.
    for conflict in DocumentConflict.objects.for_organization(revision.organization).filter(
        revision=revision, status=DocumentConflict.Status.OPEN
    ):
        blocking.append(
            _item(
                "document_conflict",
                conflict,
                conflict.kind,
                "Contradiction documentaire : décision humaine requise avant validation.",
                "Relations documentaires",
            )
        )

    goods_lines = list(revision.goods_lines.all())
    if invoices and not goods_lines:
        blocking.append(
            _item(
                "revision", revision, "goods_lines", "Aucune marchandise préparée.", f"Révision {revision.revision_no}"
            )
        )
    for goods in goods_lines:
        label = f"Marchandise {goods.ordinal}"
        decision = services.current_decision(goods)
        if decision is None:
            blocking.append(_item("goods_line", goods, "code", "Code douanier à contrôler et confirmer.", label))
        elif not services.decision_is_current(decision, goods):
            blocking.append(
                _item("goods_line", goods, "code", "Données modifiées depuis la décision : code à revoir.", label)
            )
        if not goods.origin_country:
            blocking.append(_item("goods_line", goods, "origin_country", "Origine à renseigner.", label))
        # Sans régime de dossier, le manque est déjà signalé une fois pour la révision.
    return {"blocking": blocking, "warnings": warnings, "complete": not blocking}
