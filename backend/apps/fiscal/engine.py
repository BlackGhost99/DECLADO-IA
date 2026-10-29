"""Moteur de calcul (TAX-02, TAX-06) : fonctions pures en Decimal, sans base de données.

Inconnu n'est jamais zéro : une valeur ou un taux inconnu rend inconnues la taxe et celles qui
en dépendent, et le total n'est alors pas affiché comme complet (seule la somme connue l'est).
"""

from dataclasses import dataclass, field
from decimal import Decimal

from . import rules

ZERO = Decimal("0")


@dataclass
class TaxAmount:
    code: str
    base_kind: str
    base: Decimal | None
    rate: Decimal | None
    amount: Decimal | None
    reason: str = ""


@dataclass
class Article:
    amounts: list[TaxAmount]
    total: Decimal | None
    known_total: Decimal
    unknown: list[str] = field(default_factory=list)


def _base(kind: str, value: Decimal | None, amounts: dict[str, Decimal | None]) -> Decimal | None:
    if value is None:
        return None
    parts = {rules.VALUE: (), rules.VALUE_DDI: ("DDI",), rules.VALUE_DDI_DA: ("DDI", "DA")}[kind]
    if any(amounts.get(p) is None for p in parts):
        return None
    return value + sum((amounts[p] for p in parts), ZERO)


def compute_article(value: Decimal | None, rates: dict[str, Decimal | None], reasons: dict[str, str] | None = None):
    """Taxes d'un article pour une valeur en douane en XAF et des taux en %.

    `rates[code]` vaut None quand le taux est inconnu ; un droit d'accise absent est passé à 0.
    """
    reasons = reasons or {}
    amounts: dict[str, Decimal | None] = {}
    lines = []
    for rule in rules.ARTICLE_TAXES:
        rate = rates.get(rule.code)
        base = _base(rule.base, value, amounts)
        if base is None or rate is None:
            amount = None
            if rate is None:
                reason = reasons.get(rule.code) or "Taux inconnu."
            elif value is None:
                reason = "Valeur en douane inconnue."
            else:
                reason = "Dépend d'une taxe inconnue."
        else:
            amount = rules.round_tax(base * rate / rules.HUNDRED)
            reason = ""
        amounts[rule.code] = amount
        lines.append(TaxAmount(rule.code, rule.base, base, rate, amount, reason))
    return _article(lines)


def _article(lines: list[TaxAmount]) -> Article:
    unknown = [t.code for t in lines if t.amount is None]
    known = sum((t.amount for t in lines if t.amount is not None), ZERO)
    return Article(lines, None if unknown else known, known, unknown)


def compute_global(total_value: Decimal | None, rates: dict[str, Decimal | None]) -> list[TaxAmount]:
    """Taxes globales de la déclaration (redevance informatique), sur la valeur totale."""
    out = []
    for code in rules.GLOBAL_TAXES:
        rate = rates.get(code)
        if rate is None or total_value is None:
            reason = "Taux à saisir par l'admin ClairTransit." if rate is None else "Valeur en douane inconnue."
            out.append(TaxAmount(code, rules.VALUE, total_value, rate, None, reason))
        else:
            out.append(
                TaxAmount(code, rules.VALUE, total_value, rate, rules.round_tax(total_value * rate / rules.HUNDRED))
            )
    return out


def declaration_total(articles: list[Article], global_taxes: list[TaxAmount]) -> dict:
    known = sum((a.known_total for a in articles), ZERO) + sum(
        (t.amount for t in global_taxes if t.amount is not None), ZERO
    )
    complete = all(a.total is not None for a in articles) and all(t.amount is not None for t in global_taxes)
    by_tax: dict[str, Decimal | None] = {}
    for article in articles:
        for t in article.amounts:
            if t.code in by_tax and by_tax[t.code] is None:
                continue
            by_tax[t.code] = None if t.amount is None else by_tax.get(t.code, ZERO) + t.amount
    for t in global_taxes:
        by_tax[t.code] = t.amount
    return {"total": known if complete and articles else None, "known_total": known, "by_tax": by_tax}
