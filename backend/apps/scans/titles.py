"""Reconnaissance du type d'une page numérisée d'après son titre (NUM-04).

Seul le haut de la page est examiné : c'est là que figure le titre d'une pièce. Le résultat est
une proposition accompagnée du texte lu ; il ne vaut jamais décision.
"""

import re
import unicodedata
from dataclasses import dataclass

# Part de la hauteur de page où l'on cherche un titre.
TITLE_ZONE = 0.4

INVOICE, TRANSPORT, PACKING, ORIGIN, OTHER = "invoice", "transport", "packing_list", "origin", "other"

# (type, libellé affiché, motif sur texte en majuscules sans accents)
TITLES = [
    (PACKING, "Liste de colisage", r"\bPACKING ?LIST\b|\bLISTE DE COLISAGE\b"),
    (ORIGIN, "Certificat d'origine", r"\bCERTIFICAT D ?ORIGINE\b|\bCERTIFICATE OF ORIGIN\b"),
    (
        TRANSPORT,
        "Document de transport",
        r"\bBILL OF LADING\b|\bCONNAISSEMENT\b|\bAIR ?WAY ?BILL\b|\bSEA ?WAY ?BILL\b"
        r"|\bLETTRE DE TRANSPORT AERIEN\b|\bLETTRE DE VOITURE\b",
    ),
    (
        OTHER,
        "Attestation d'assurance",
        r"\bATTESTATION D ?ASSURANCE\b|\bCERTIFICAT D ?ASSURANCE\b|\bINSURANCE CERTIFICATE\b|\bPOLICE D ?ASSURANCE\b",
    ),
    (INVOICE, "Facture", r"\b(?:COMMERCIAL |PRO ?FORMA )?INVOICE\b|\bFACTURE\b"),
]
_REFERENCE = re.compile(r"\b(?:N\s?[O°º]|NO\.?|NUMERO|NUMBER|REF)\s*[:.#]?\s*([A-Z0-9][A-Z0-9/.\-]*\d[A-Z0-9/.\-]*)")
_MARKER = re.compile(r"\bPAGE\s*(\d{1,3})\s*(?:/|SUR|OF|DE)\s*(\d{1,3})\b")


@dataclass
class Word:
    text: str
    top: float  # position verticale relative (0 = haut de page, 1 = bas)
    left: float = 0.0


@dataclass
class PageReading:
    usage: str = ""
    title: str = ""  # texte tel que lu, pour expliquer la proposition
    label: str = ""  # libellé du type proposé
    reference: str = ""
    marker: tuple[int, int] | None = None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("'", " ").upper()
    return re.sub(r"\s+", " ", text).strip()


def ordered_text(words: list[Word], *, zone: float | None = None) -> str:
    """Texte dans l'ordre de lecture (lignes de haut en bas, puis de gauche à droite)."""
    kept = [w for w in words if zone is None or w.top <= zone]
    kept.sort(key=lambda w: (round(w.top * 100), w.left))
    return " ".join(w.text for w in kept)


def read_page(words: list[Word]) -> PageReading:
    reading = PageReading()
    top = ordered_text(words, zone=TITLE_ZONE)
    top_norm = normalize(top)
    best = None
    for usage, label, pattern in TITLES:
        match = re.search(pattern, top_norm)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), usage, label, match.group(0))
    if best:
        _, reading.usage, reading.label, reading.title = best
    ref = _REFERENCE.search(top_norm)
    if ref:
        reading.reference = ref.group(1).strip(".-/")
    marker = _MARKER.search(normalize(ordered_text(words)))
    if marker:
        current, total = int(marker.group(1)), int(marker.group(2))
        if 1 <= current <= total:
            reading.marker = (current, total)
    return reading
