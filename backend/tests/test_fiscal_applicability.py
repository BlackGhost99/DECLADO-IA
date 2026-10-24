from datetime import date
from decimal import Decimal

import pytest

from apps.cases.fiscal_applicability import VerifiedFiscalRule, select_applicable_rules
from apps.cases.tax_engine import TaxInputError, calculate


def rule(*, published=True, valid_to=None, territory="GA"):
    return VerifiedFiscalRule(
        code="TEST", rate_percent=Decimal("5"), base="customs_value",
        territory=territory, regime="IM4", tariff_code="01011000",
        valid_from=date(2026, 1, 1), valid_to=valid_to,
        legal_reference="FICTIONAL-TEST", verification_id="TEST-ONLY",
        published=published,
    )


def test_exact_country_regime_code_and_dates():
    selected = select_applicable_rules(
        rules=[rule()], territory="GA", regime="IM4",
        tariff_code="01011000", on_date=date(2026, 2, 1),
    )
    assert calculate(customs_value="100", rules=selected)["total_charges"] == "5"


@pytest.mark.parametrize("kwargs", [
    {"territory": "CM"},
    {"regime": "EX1"},
    {"tariff_code": "99999999"},
    {"on_date": date(2025, 12, 31)},
])
def test_inapplicable_scope_is_rejected(kwargs):
    defaults = {
        "rules": [rule()], "territory": "GA", "regime": "IM4",
        "tariff_code": "01011000", "on_date": date(2026, 2, 1),
    }
    defaults.update(kwargs)
    with pytest.raises(TaxInputError):
        select_applicable_rules(**defaults)


def test_unpublished_and_expired_rules_rejected():
    for candidate in (rule(published=False), rule(valid_to=date(2026, 2, 1))):
        with pytest.raises(TaxInputError):
            select_applicable_rules(
                rules=[candidate], territory="GA", regime="IM4",
                tariff_code="01011000", on_date=date(2026, 2, 1),
            )
