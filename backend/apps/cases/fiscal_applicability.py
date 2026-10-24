"""Fiscal rule applicability: legal dates, territory, customs procedure and source."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .tax_engine import TaxInputError, TaxRule, decimal_value


@dataclass(frozen=True)
class VerifiedFiscalRule:
    code: str
    rate_percent: Decimal
    base: str
    territory: str
    regime: str
    tariff_code: str
    valid_from: date
    valid_to: date | None
    legal_reference: str
    verification_id: str
    published: bool


def select_applicable_rules(*, rules, territory, regime, tariff_code, on_date):
    if not isinstance(on_date, date) or isinstance(on_date, datetime):
        raise TaxInputError("A dated fiscal assessment is mandatory.")
    selected = []
    for rule in rules:
        if not rule.published or not rule.verification_id or not rule.legal_reference:
            continue
        if rule.territory != territory or rule.regime != regime:
            continue
        if rule.tariff_code != tariff_code:
            continue
        if on_date < rule.valid_from or (rule.valid_to and on_date >= rule.valid_to):
            continue
        selected.append(TaxRule(
            code=rule.code,
            rate=decimal_value(rule.rate_percent),
            base=rule.base,
            source_id=rule.verification_id,
            verified=True,
        ))
    if not selected:
        raise TaxInputError("No legally verified fiscal rule for this exact scope.")
    if len({r.code for r in selected}) != len(selected):
        raise TaxInputError("Conflicting published rules for the same tax.")
    return tuple(selected)
