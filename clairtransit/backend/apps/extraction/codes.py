"""Nature d'un code d'après son libellé et son contexte (DEV-017, EXT-04, COD-01).

Une suite de chiffres n'est jamais prise pour un code douanier sur sa seule forme : c'est le
titre de colonne ou le libellé qui la précède qui décide. Un libellé imprécis (« Code »)
donne une observation « nature incertaine », que l'utilisateur tranche.
"""

import re

from apps.tariffs.codes import normalize_code

from .numbers import norm

CUSTOMS, SUPPLIER, AMBIGUOUS = "customs", "supplier", "ambiguous"

CUSTOMS_LABELS = (
    "hs code", "hs", "h.s.", "h.s. code", "code sh", "sh", "code douanier", "nomenclature", "tarif",
    "code tarifaire", "position tarifaire", "nomenclature douaniere", "customs code", "commodity code",
    "hts", "hts code", "tariff code", "nc", "code nc", "ngp",
)  # fmt: skip
SUPPLIER_LABELS = (
    "ref", "ref.", "reference", "ref article", "reference article", "code article", "article", "item",
    "item no", "item no.", "item code", "part no", "part no.", "part number", "sku", "product code",
    "code produit", "ref fournisseur", "ean",
)  # fmt: skip
AMBIGUOUS_LABELS = ("code", "n°", "no", "numero", "num")

# Libellé suivi d'un code dans le texte d'une désignation : « HS Code 0101.10.00 ».
INLINE_CUSTOMS = re.compile(
    r"\b(HS\s*Code|H\.S\.(?:\s*Code)?|HS|Code\s+SH|SH|Code\s+douanier|Nomenclature|Tarif|Customs\s+code|"
    r"Commodity\s+code|HTS)\s*[:#n°.]*\s*(\d[\d .]{3,16}\d)",
    re.IGNORECASE,
)


def classify_label(label: str) -> str | None:
    key = norm(label).strip(" :#.")
    if key in CUSTOMS_LABELS:
        return CUSTOMS
    if key in SUPPLIER_LABELS:
        return SUPPLIER
    if key in AMBIGUOUS_LABELS:
        return AMBIGUOUS
    return None


def claimed_scheme(label: str) -> str:
    key = norm(label)
    if re.search(r"\b(hs|h\.s\.|sh|hts)\b", key):
        return "SH (annoncé par le document)"
    if "nc" in key.split() or "ngp" in key.split():
        return "Nomenclature nationale (annoncée)"
    return ""


def code_findings(raw: str) -> list[str]:
    """Constats de forme, sans réparer le code : la vérification d'existence reste au contrôle."""
    normalized = normalize_code(raw)
    if normalized is None:
        return ["CODE_MALFORMED"]
    if len(normalized) < 6:
        return ["CODE_TOO_SHORT"]
    if len(normalized) == 6:
        return ["CODE_SIX_DIGITS"]  # SH6 : une subdivision nationale sera demandée
    if len(normalized) % 2:
        return ["CODE_ODD_LENGTH"]
    return []


def inline_codes(text: str) -> list[tuple[str, str, int, int]]:
    """Codes douaniers annoncés dans un texte : (libellé, code, début, fin)."""
    return [(m[1], m[2].strip(), m.start(), m.end()) for m in INLINE_CUSTOMS.finditer(text or "")]


FINDING_MESSAGES = {
    "CODE_MALFORMED": "Code non numérique : original conservé, aucune réparation.",
    "CODE_TOO_SHORT": "Code trop court pour être déclaré : à compléter.",
    "CODE_SIX_DIGITS": "Code à six chiffres (SH) : une subdivision du référentiel cible sera demandée.",
    "CODE_ODD_LENGTH": "Longueur inhabituelle : vérifier la lecture.",
    "CODE_CONFLICT": "Deux codes douaniers différents sur la même ligne : à trancher.",
    "CODE_NUMERIC_CELL": "Cellule Excel numérique : des zéros initiaux ont pu être perdus. Aucun zéro ajouté.",
    "CODE_ABSENT": "Aucun code douanier sur la ligne : la référence article n'en tient pas lieu.",
}
