"""Règles de calcul des taxes à l'importation (TAX-02, TAX-03) : déterministes et versionnées.

Les bases et l'arrondi viennent de la formule « Taux cumulé » du classeur Tarif CEMAC 2022 SWD
et ont été vérifiés sur une déclaration réelle (base 549 070, DDI 10 % : chaque montant
retrouvé au franc). Un LLM n'intervient jamais ici.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from .models import TaxCode

RULES_VERSION = "2022-swd-2"  # 2 : TCI au compte 2 hors total, RI calculée par SYDONIA

VALUE = "value"  # valeur en douane
VALUE_DDI = "value_ddi"  # valeur + DDI
VALUE_DDI_DA = "value_ddi_da"  # valeur + DDI + droit d'accise

BASE_LABELS = {
    VALUE: "Valeur en douane",
    VALUE_DDI: "Valeur + DDI",
    VALUE_DDI_DA: "Valeur + DDI + DA",
}


@dataclass(frozen=True)
class TaxRule:
    code: str
    base: str
    column: str  # en-tête de colonne dans la feuille SWD
    # Taxe lue sur la déclaration réelle qui a servi à vérifier la règle.
    verified: bool = True
    # Vide dans la feuille = pas de taxe (seul le droit d'accise : il ne frappe que certains produits).
    empty_means_none: bool = False
    # Compte de paiement : le total de l'article ne compte que le compte 1 (déclarant, 30/10/2026).
    account: int = 1


ARTICLE_TAXES = (
    TaxRule(TaxCode.DDI, VALUE, "DDI"),
    TaxRule(TaxCode.DA, VALUE_DDI, "DAC", verified=False, empty_means_none=True),
    TaxRule(TaxCode.TVA, VALUE_DDI_DA, "TVA"),
    TaxRule(TaxCode.TCI, VALUE, "TCI", account=2),
    TaxRule(TaxCode.CCI, VALUE, "CCI"),
    TaxRule(TaxCode.OAD, VALUE, "OAD"),
    TaxRule(TaxCode.CSS, VALUE_DDI_DA, "CSS"),
    TaxRule(TaxCode.CAF, VALUE, "CAF"),
)
RULES = {r.code: r for r in ARTICLE_TAXES}
# Colonnes de taux de la feuille SWD, dans l'ordre (DSO : droit de sortie, hors calcul import).
SHEET_COLUMNS = ("DDI", "DSO", "DAC", "TVA", "TCI", "CCI", "OAD", "CSS", "CAF")
COLUMN_TAX = dict(zip(SHEET_COLUMNS, ("DDI", "DSO", "DA", "TVA", "TCI", "CCI", "OAD", "CSS", "CAF"), strict=True))
# Taxe globale de la déclaration, calculée par SYDONIA selon ses propres critères (montant non fixe) :
# ClairTransit ne la calcule pas et ne la compte pas dans le total.
GLOBAL_TAXES = (TaxCode.RI,)
SYDONIA_TAXES = (TaxCode.RI,)
EXPORT_ONLY = (TaxCode.DSO,)

NOTES = {
    TaxCode.TCI: (
        "Taxe spéciale versée sur un compte distinct (compte 2) : affichée à part, hors du total de l'article."
    ),
    TaxCode.RI: (
        "Redevance pour l'usage de SYDONIA, calculée par SYDONIA selon ses propres critères (montant non fixe) : "
        "ClairTransit ne la calcule pas et ne la compte pas dans le total."
    ),
    TaxCode.DSO: "Droit de sortie : ne s'applique pas à une importation.",
}

ONE = Decimal("1")
HUNDRED = Decimal("100")


def round_tax(amount: Decimal) -> Decimal:
    """Chaque taxe est arrondie au franc supérieur (vérifié : 274,535 → 275, 108 715,86 → 108 716)."""
    return amount.quantize(ONE, rounding=ROUND_CEILING)


def cumulative_rate(rates: dict[str, Decimal | None]) -> Decimal | None:
    """Taux cumulé selon la formule du classeur SWD, en % de la valeur ; inconnu si un taux l'est."""
    values = {}
    for rule in ARTICLE_TAXES:
        rate = rates.get(rule.code)
        if rate is None:
            if not rule.empty_means_none:
                return None
            rate = Decimal("0")
        values[rule.code] = rate
    ddi, da = values["DDI"], (HUNDRED + values["DDI"]) * values["DA"] / HUNDRED
    after_da = HUNDRED + ddi + da
    return (
        ddi
        + da
        + after_da * values["TVA"] / HUNDRED
        + values["TCI"]
        + values["CCI"]
        + values["OAD"]
        + after_da * values["CSS"] / HUNDRED
        + values["CAF"]
    )
