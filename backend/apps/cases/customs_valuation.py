"""Auditable valuation arithmetic, not a legal determination of customs value."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .tax_engine import TaxInputError, decimal_value


@dataclass(frozen=True)
class ExchangeRate:
    from_currency: str
    to_currency: str
    factor: Decimal
    rate_date: str
    source_reference: str
    verified: bool = False


def convert(amount, rate: ExchangeRate, *, quantum="1"):
    if not rate.verified or not rate.source_reference or not rate.rate_date:
        raise TaxInputError("A verified and dated exchange rate is required.")
    factor = decimal_value(rate.factor)
    if factor <= 0:
        raise TaxInputError("Exchange rate must be positive.")
    if len(rate.from_currency) != 3 or len(rate.to_currency) != 3:
        raise TaxInputError("Invalid currency codes.")
    value = decimal_value(amount)
    if value < 0:
        raise TaxInputError("Negative amounts require explicit adjustment handling.")
    return (value * factor).quantize(decimal_value(quantum), rounding=ROUND_HALF_UP)


def distribute(amount, weighted_items, *, quantum="1"):
    """Largest remainder allocation; shares always reconcile to the charge."""
    total = decimal_value(amount)
    unit = decimal_value(quantum)
    if total < 0 or unit <= 0 or total % unit:
        raise TaxInputError("Amount must be nonnegative and divisible by quantum.")
    if not weighted_items:
        raise TaxInputError("At least one goods line is required.")
    keys = [key for key, weight in weighted_items]
    if len(keys) != len(set(keys)):
        raise TaxInputError("Duplicate goods line key.")
    weights = [decimal_value(weight) for _, weight in weighted_items]
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise TaxInputError("At least one positive weight is required.")
    shares = [total * weight / sum(weights) for weight in weights]
    floors = [(share // unit) * unit for share in shares]
    remainder_units = int((total - sum(floors)) / unit)
    order = sorted(range(len(keys)), key=lambda i: (-(shares[i] - floors[i]), i))
    for i in order[:remainder_units]:
        floors[i] += unit
    return {key: str(share) for key, share in zip(keys, floors)}


def valuation_preview(*, merchandise_amount, freight_amount, insurance_amount, adjustment_amount="0"):
    """Simple addition only; legal inclusion/exclusion still requires expert review."""
    values = [decimal_value(item) for item in (
        merchandise_amount, freight_amount, insurance_amount, adjustment_amount,
    )]
    if any(item < 0 for item in values[:3]):
        raise TaxInputError("Merchandise, freight and insurance must be nonnegative.")
    amount = sum(values)
    if amount < 0:
        raise TaxInputError("Final valuation cannot be negative.")
    return {"merchandise": str(values[0]), "freight": str(values[1]),
            "insurance": str(values[2]), "adjustments": str(values[3]),
            "provisional_customs_value": str(amount),
            "status": "unverified_valuation_preview"}
