from decimal import Decimal

import pytest

from apps.cases.tax_engine import TaxInputError, TaxRule, calculate


def rule(code, rate, base="customs_value", verified=True, source="verified-rule-1"):
    return TaxRule(code, Decimal(rate), base, source, verified)


def test_decimals_and_dependency_order():
    result = calculate(customs_value="10000", rules=[
        rule("B", "10", "customs_value_plus_duties"),
        rule("A", "5"),
    ])
    assert result["total_charges"] == "1550"
    assert [line["code"] for line in result["charges"]] == ["A", "B"]
    assert result["status"] == "mathematical_calculation_only"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-5", 0.1])
def test_invalid_customs_value(amount):
    with pytest.raises(TaxInputError):
        calculate(customs_value=amount, rules=[rule("A", "5")])


def test_refuses_unverified_rates():
    with pytest.raises(TaxInputError):
        calculate(customs_value="100", rules=[rule("A", "5", verified=False)])


def test_refuses_duplicate_codes():
    with pytest.raises(TaxInputError):
        calculate(customs_value="100", rules=[rule("A", "5"), rule("A", "3")])


def test_refuses_missing_rules():
    with pytest.raises(TaxInputError):
        calculate(customs_value="100", rules=[])


def test_exact_half_up_rounding():
    result = calculate(customs_value="5", rules=[rule("A", "10")])
    assert result["total_charges"] == "1"
