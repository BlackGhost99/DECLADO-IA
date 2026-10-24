from decimal import Decimal

import pytest

from apps.cases.customs_valuation import ExchangeRate, convert, distribute, valuation_preview
from apps.cases.tax_engine import TaxInputError


def test_exchange_requires_verified_source():
    with pytest.raises(TaxInputError):
        convert("100", ExchangeRate("EUR", "XAF", Decimal("655"), "2026-01-01", "EXAMPLE", False))


def test_exchange_math_is_deterministic():
    rate = ExchangeRate("EUR", "XAF", Decimal("655.957"), "2026-01-01", "FAKE-TEST", True)
    assert convert("2", rate) == Decimal("1312")


def test_allocations_reconcile_and_preserve_order():
    assert distribute("10", [("a", "1"), ("b", "1"), ("c", "1")]) == {
        "a": "4", "b": "3", "c": "3",
    }


def test_fractional_weights():
    result = distribute("100", [("a", "0.25"), ("b", "0.75")])
    assert result == {"a": "25", "b": "75"}


def test_no_double_charge_in_valuation():
    result = valuation_preview(
        merchandise_amount="100", freight_amount="15", insurance_amount="5",
    )
    assert result["provisional_customs_value"] == "120"
    assert result["status"] == "unverified_valuation_preview"
