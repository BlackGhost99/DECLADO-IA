"""Deterministic calculation kernel. Rules are explicit, verified inputs, NOT tariff observations.

The kernel does not assert regulatory applicability. A separate fiscal-rule
publication workflow must certify rates, dates, country, regime and legal sources.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class TaxInputError(ValueError):
    pass


@dataclass(frozen=True)
class TaxRule:
    code: str
    rate: Decimal  # percent
    base: str  # customs_value, customs_value_plus_duties
    source_id: str
    verified: bool = False


def decimal_value(value):
    if isinstance(value, float) or isinstance(value, bool):
        raise TaxInputError("Float/bool inputs are forbidden; supply decimal strings.")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TaxInputError("Invalid decimal amount.") from exc
    if not result.is_finite():
        raise TaxInputError("Non-finite amount.")
    return result


def calculate(*, customs_value, rules, currency="XAF", quantum="1"):
    """Compute a transparent breakdown, requiring an explicitly verified rule set.

    The caller remains responsible for verifying legal applicability, exemptions,
    valuation, exchange rate, and all mandatory taxes.
    """
    base_value = decimal_value(customs_value)
    rounding = decimal_value(quantum)
    if base_value < 0 or rounding <= 0:
        raise TaxInputError("Negative customs value or invalid rounding.")
    if not currency or len(currency) != 3 or not currency.isalpha():
        raise TaxInputError("Currency must be an ISO-style three-letter code.")
    if not rules:
        raise TaxInputError("No applicable verified fiscal rules supplied.")
    normalized = []
    seen = set()
    for rule in rules:
        if not rule.verified or not rule.source_id:
            raise TaxInputError("Unverified or untraceable rate.")
        rate = decimal_value(rule.rate)
        if not rule.code or rule.code in seen or not (Decimal("0") <= rate <= Decimal("100")):
            raise TaxInputError("Duplicate tax code or invalid rate.")
        if rule.base not in {"customs_value", "customs_value_plus_duties"}:
            raise TaxInputError("Unsupported tax base.")
        seen.add(rule.code)
        normalized.append((rule, rate))
    # Duties are computed first so other levies can reference their sum,
    # regardless of the caller's ordering.
    duties = []
    for rule, rate in normalized:
        if rule.base == "customs_value":
            raw = base_value * rate / Decimal("100")
            amount = raw.quantize(rounding, rounding=ROUND_HALF_UP)
            duties.append({"code": rule.code, "rate_percent": str(rate),
                           "base": str(base_value), "amount": str(amount),
                           "source_id": rule.source_id})
    duty_total = sum((Decimal(x["amount"]) for x in duties), Decimal("0"))
    other = []
    for rule, rate in normalized:
        if rule.base == "customs_value_plus_duties":
            basis = base_value + duty_total
            amount = (basis * rate / Decimal("100")).quantize(rounding, rounding=ROUND_HALF_UP)
            other.append({"code": rule.code, "rate_percent": str(rate),
                          "base": str(basis), "amount": str(amount),
                          "source_id": rule.source_id})
    lines = duties + other
    total = sum((Decimal(x["amount"]) for x in lines), Decimal("0"))
    return {"currency": currency.upper(), "customs_value": str(base_value),
            "charges": lines, "total_charges": str(total),
            "landed_value_before_other_costs": str(base_value + total),
            "status": "mathematical_calculation_only"}
