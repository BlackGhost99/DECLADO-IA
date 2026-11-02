"""Colis et masses du dossier : colis et masse brute lus sur les titres de transport (B/L, LTA,
lettre de voiture), masse nette lue sur les listes de colisage.

Rien n'est deviné : seule une valeur imprimée sur la pièce (ou saisie par l'agent à la place de
la lecture) est reprise. Une masse n'est retenue qu'en kilogrammes ; une autre unité reste à
saisir. Un total n'est donné que si chaque titre de transport du dossier a sa valeur : un total
partiel serait faux. Une masse n'est jamais répartie entre plusieurs articles.
"""

import re
from decimal import Decimal

from apps.extraction import readers
from apps.extraction.api import document_fields
from apps.extraction.models import ExtractionRun
from apps.extraction.numbers import parse_amount

from .models import CaseDocument

_SPACES = "    "
WEIGHT = re.compile(r"^\s*([\d" + _SPACES + r".,]+)\s*(kgs?|kgm|kilos?|kilogrammes?)\.?\s*$", re.IGNORECASE)
PACKAGES = re.compile(r"^\s*(\d[\d" + _SPACES + r"]*)\s*(.*?)\s*$")


def weight_kg(raw: str) -> Decimal | None:
    """« 3 940 kg » → 3940 ; une autre unité (t, lbs) ou un nombre ambigu → inconnu."""
    m = WEIGHT.match(raw or "")
    if not m:
        return None
    value = parse_amount(m[1]).value
    return value if value is not None and value > 0 else None


def packages(raw: str) -> tuple[int | None, str]:
    """« 9 caisses bois » → (9, « caisses bois ») ; sans nombre en tête → inconnu."""
    m = PACKAGES.match(raw or "")
    if not m:
        return None, ""
    count = int(re.sub(r"\D", "", m[1]))
    return (count, m[2]) if count > 0 else (None, "")


def _retained(fields: list[dict], name: str) -> str:
    for f in fields:
        if f["field"] == name:
            entered = f.get("entered") or {}
            return str(entered.get("raw") or f.get("raw") or "")
    return ""


def transport_measures(revision) -> dict:
    """Colis et masse brute par titre de transport, et leurs totaux quand chacun est connu."""
    links = revision.documents.filter(usage=CaseDocument.Usage.TRANSPORT, replaced_by__isnull=True).select_related(
        "document"
    )
    pieces, seen = [], set()
    for link in links.order_by("created_at"):
        run = (
            ExtractionRun.objects.filter(case_document=link, status=ExtractionRun.Status.SUCCEEDED)
            .order_by("-created_at")
            .first()
        )
        if run is None or run.options.get("reader") != readers.TRANSPORT:
            pieces.append({"reference": "", "title": link.document.original_name, "read": False})
            continue
        fields = document_fields(run)
        number = _retained(fields, "transport_number")
        if number and number in seen:
            continue  # même titre déposé deux fois : compté une fois
        seen.add(number)
        raw_packages, raw_weight = _retained(fields, "packages"), _retained(fields, "gross_weight")
        count, nature = packages(raw_packages)
        pieces.append(
            {
                "reference": number,
                "title": link.document.original_name,
                "read": True,
                "packages_raw": raw_packages,
                "packages": count,
                "nature": nature,
                "gross_weight_raw": raw_weight,
                "gross_weight_kg": weight_kg(raw_weight),
            }
        )
    complete = bool(pieces) and all(p["read"] for p in pieces)
    counts = [p.get("packages") for p in pieces]
    weights = [p.get("gross_weight_kg") for p in pieces]
    natures = {p["nature"].lower() for p in pieces if p.get("nature")}
    return {
        "pieces": pieces,
        "packages": sum(counts) if complete and None not in counts else None,
        "nature": next(iter(natures)) if len(natures) == 1 else "",
        "gross_weight_kg": sum(weights, Decimal("0")) if complete and None not in weights else None,
    }


def packing_net_weight(revision) -> Decimal | None:
    """Masse nette totale des listes de colisage ; inconnue si une liste n'est pas lue ou ne l'imprime pas."""
    links = revision.documents.filter(usage=CaseDocument.Usage.PACKING_LIST, replaced_by__isnull=True)
    weights, seen = [], set()
    for link in links.order_by("created_at"):
        run = (
            ExtractionRun.objects.filter(case_document=link, status=ExtractionRun.Status.SUCCEEDED)
            .order_by("-created_at")
            .first()
        )
        if run is None or run.options.get("reader") != readers.PACKING:
            return None
        fields = document_fields(run)
        number = _retained(fields, "document_number")
        if number and number in seen:
            continue
        seen.add(number)
        weights.append(weight_kg(_retained(fields, "net_weight")))
    if not weights or None in weights:
        return None
    return sum(weights, Decimal("0"))


def measures_payload(revision) -> dict:
    m = transport_measures(revision)
    weight = m["gross_weight_kg"]
    net = packing_net_weight(revision)
    return {
        "net_weight_kg": None if net is None else format(net.normalize(), "f"),
        "packages": m["packages"],
        "nature": m["nature"],
        "gross_weight_kg": None if weight is None else format(weight.normalize(), "f"),
        "sources": [p["reference"] or p["title"] for p in m["pieces"]],
    }
