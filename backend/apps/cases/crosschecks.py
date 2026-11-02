"""Contrôles croisés entre les pièces d'un dossier (CTL-08) : des écarts à vérifier, jamais bloquants.

Chaque contrôle compare des valeurs imprimées (ou saisies par l'agent à la place de la lecture) :
- une pièce (B/L, assurance, fret, colisage, certificat d'origine) qui cite une facture absente
  du dossier : pièce d'un autre envoi, ou facture manquante ;
- une valeur assurée inférieure au total des factures, dans la même devise ;
- un pays d'origine du certificat différent de l'origine d'une marchandise ;
- une masse brute différente entre le titre de transport et la liste de colisage ;
- un conteneur imprimé sur la liste de colisage et absent du titre de transport, ou l'inverse ;
- un scellé lu sur la liste de colisage introuvable sur le titre de transport, et inversement.

Une valeur inconnue ne déclenche rien : on ne signale que ce qui est lu des deux côtés.
"""

import re
from decimal import Decimal

from apps.extraction import readers
from apps.extraction.api import document_fields
from apps.extraction.models import ExtractionRun
from apps.extraction.numbers import parse_amount, parse_country, parse_currency

from . import measures
from .models import CaseDocument

USAGE_LABELS = dict(CaseDocument.Usage.choices)
# Écart de masse toléré entre deux pièces (arrondis, tare) avant de le signaler.
WEIGHT_TOLERANCE = Decimal("0.01")


def _key(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _value(fields: list[dict], name: str) -> str:
    for f in fields:
        if f["field"] == name:
            entered = f.get("entered") or {}
            if entered.get("raw"):
                return str(entered["raw"])
            return str(f.get("raw") or "") if f.get("status") == "ok" else ""
    return ""


def _readings(revision):
    """(pièce, lecture, champs) des pièces lues autres que les factures commerciales."""
    links = revision.documents.filter(replaced_by__isnull=True).select_related("document").order_by("created_at")
    out = []
    for link in links:
        run = (
            ExtractionRun.objects.filter(case_document=link, status=ExtractionRun.Status.SUCCEEDED)
            .order_by("-created_at")
            .first()
        )
        if run is None:
            continue
        reader = run.options.get("reader", readers.INVOICE)
        if reader == readers.INVOICE:
            continue
        out.append((link, reader, document_fields(run), run.read_text or ""))
    return out


def _containers(fields: list[dict], text: str) -> dict[str, str]:
    """{propriétaire + n° de série : forme imprimée} de tous les conteneurs cités par la pièce.

    Le chiffre de contrôle ISO 6346 est parfois omis : on compare sans lui."""
    found = {}
    for raw in (_value(fields, "container"), text):
        for match in readers.CONTAINER.finditer(raw.upper()):
            found.setdefault(_key(match.group(0))[:10], match.group(0))
    return found


def _container_warnings(transport, packing) -> list[dict]:
    on_bl = {k: v for _lk, f, text in transport for k, v in _containers(f, text).items()}
    per_pl = [(lk, _containers(f, text)) for lk, f, text in packing]
    on_pl = {k: v for _lk, found in per_pl for k, v in found.items()}
    if not on_bl or not on_pl:
        return []
    out = []
    for link, found in per_pl:
        missing = sorted(v for k, v in found.items() if k not in on_bl)
        if missing:
            out.append(
                _item(link, "container",
                      f"Conteneur {', '.join(missing)} absent du titre de transport "
                      f"({', '.join(sorted(on_bl.values()))}) : pièce d'un autre envoi ?")
            )  # fmt: skip
    if len(transport) == 1:
        missing = sorted(v for k, v in on_bl.items() if k not in on_pl)
        if missing:
            out.append(
                _item(transport[0][0], "container",
                      f"Conteneur {', '.join(missing)} du titre de transport absent de la liste de colisage : "
                      "liste incomplète ou manquante ?")
            )  # fmt: skip
    return out


def _seal_warnings(transport, packing) -> list[dict]:
    """Scellé différent : seulement s'il est lu des deux côtés et introuvable dans le texte de l'autre pièce
    (un titre de transport à plusieurs conteneurs imprime plusieurs scellés)."""
    if len(transport) != 1:
        return []
    _bl, bl_fields, bl_text = transport[0]
    bl_seal = _value(bl_fields, "seal")
    if not _key(bl_seal):
        return []
    out = []
    for link, fields, text in packing:
        seal = _value(fields, "seal")
        if not _key(seal) or _key(seal) == _key(bl_seal):
            continue
        if _key(seal) in _key(bl_text) or _key(bl_seal) in _key(text):
            continue
        out.append(_item(link, "seal", f"Scellé {seal}, le titre de transport indique {bl_seal}."))
    return out


def _item(link, field, message):
    label = f"{USAGE_LABELS.get(link.usage, 'Pièce')} « {link.document.original_name} »"
    return {"scope": "case_document", "id": str(link.id), "label": label, "field": field, "message": message}


def evaluate(revision) -> list[dict]:
    warnings: list[dict] = []
    invoices = list(revision.invoices.all())
    numbers = {_key(inv.invoice_number) for inv in invoices if _key(inv.invoice_number)}
    currencies = {(inv.currency or "").upper() for inv in invoices if inv.currency}
    totals = [inv.declared_total for inv in invoices]
    invoice_total = sum(totals, Decimal("0")) if totals and None not in totals and len(currencies) == 1 else None
    origins = {g.ordinal: g.origin_country.upper() for g in revision.goods_lines.all() if g.origin_country}
    readings = _readings(revision)

    for link, reader, fields, _text in readings:
        cited = _value(fields, "related_invoice")
        if cited and numbers and _key(cited) not in numbers:
            warnings.append(
                _item(link, "related_invoice",
                      f"Cite la facture « {cited} », absente du dossier : "
                      "pièce d'un autre envoi ou facture manquante ?")
            )  # fmt: skip
        if reader == readers.INSURANCE and invoice_total is not None:
            insured = parse_amount(_value(fields, "insured_value")).value
            currency = parse_currency(_value(fields, "currency")).value or ""
            invoice_currency = next(iter(currencies))
            if insured is not None and currency.upper() == invoice_currency and insured < invoice_total:
                warnings.append(
                    _item(link, "insured_value",
                          f"Valeur assurée {format(insured.normalize(), 'f')} {currency.upper()} inférieure au total "
                          f"des factures {format(invoice_total.normalize(), 'f')} {invoice_currency} : "
                          "sous-assurance ou pièce d'un autre envoi ?")
                )  # fmt: skip
        if reader == readers.ORIGIN and origins:
            country = parse_country(_value(fields, "country_of_origin")).value
            differing = sorted(n for n, o in origins.items() if country and o != country)
            if differing:
                listed = ", ".join(f"marchandise {n} : {origins[n]}" for n in differing)
                warnings.append(
                    _item(link, "country_of_origin",
                          f"Le certificat indique l'origine {country}, différente de {listed}.")
                )  # fmt: skip

    transport = [(lk, f, t) for lk, r, f, t in readings if r == readers.TRANSPORT]
    packing = [(lk, f, t) for lk, r, f, t in readings if r == readers.PACKING]
    warnings += _container_warnings(transport, packing)
    warnings += _seal_warnings(transport, packing)
    if len(transport) == 1 and len(packing) == 1:
        (_bl, bl_fields, _t), (pl, pl_fields, _u) = transport[0], packing[0]
        a = measures.weight_kg(_value(bl_fields, "gross_weight"))
        b = measures.weight_kg(_value(pl_fields, "gross_weight"))
        if a is not None and b is not None and abs(a - b) > WEIGHT_TOLERANCE * max(a, b):
            warnings.append(
                _item(pl, "gross_weight",
                      f"Masse brute {format(b.normalize(), 'f')} kg, le titre de transport indique "
                      f"{format(a.normalize(), 'f')} kg.")
            )  # fmt: skip
    return warnings
