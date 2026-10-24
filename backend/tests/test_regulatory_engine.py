"""Tests purs du moteur ; ne nécessitent pas d'accès à PostgreSQL."""
from datetime import date
from types import SimpleNamespace as O

import pytest

from apps.regulations.engine import CaseContext, UnresolvedRegulatoryCondition, evaluate_requirements


@pytest.fixture
def ctx():
    return CaseContext("GA", "import", "consumption", "sea", date(2026, 10, 24))


def rule(**kwargs):
    base = dict(
        pk=1, published=True, verified=True, valid_from=date(2022, 11, 1), valid_until=None,
        operation="import", regime="consumption", transport_mode="", conditions={},
        stage="declaration", source=O(scope="CEMAC", country_code="", reference="CEMAC-11/22"),
        document_type=O(code="commercial_invoice"), article="2a",
    )
    base.update(kwargs)
    return O(**base)


def test_organization_cannot_remove_legal_rule(ctx):
    policy = O(pk=3, active=True, document_type=O(code="freight_invoice"),
               operation="", regime="", transport_mode="")
    result = evaluate_requirements(ctx, [rule()], [policy])
    assert {x["document_type"] for x in result} == {"commercial_invoice", "freight_invoice"}
    assert result[0]["reasons"][0]["kind"] == "regulation"


def test_only_published_and_verified(ctx):
    assert evaluate_requirements(ctx, [rule(published=False), rule(verified=False)]) == []


def test_national_scope_and_dates(ctx):
    national = O(scope="NATIONAL", country_code="CM", reference="CM-X")
    assert evaluate_requirements(ctx, [rule(source=national)]) == []
    assert evaluate_requirements(ctx, [rule(valid_until=date(2025, 1, 1))]) == []


def test_conditional_previous_regime(ctx):
    legal = rule(conditions={"requires_previous_regime": True})
    absent = CaseContext("GA", "import", "consumption", "sea", ctx.declaration_date, has_previous_regime=False)
    selected = CaseContext("GA", "import", "consumption", "sea", ctx.declaration_date, has_previous_regime=True)
    assert evaluate_requirements(absent, [legal]) == []
    assert len(evaluate_requirements(selected, [legal])) == 1


def test_unknown_condition_fails_closed(ctx):
    with pytest.raises(UnresolvedRegulatoryCondition):
        evaluate_requirements(ctx, [rule(conditions={"python_expression": "True"})])


def test_unknown_fact_is_not_assumed_false(ctx):
    with pytest.raises(UnresolvedRegulatoryCondition):
        evaluate_requirements(ctx, [rule(conditions={"requires_previous_regime": True})])


def test_non_cemac_country_blocked(ctx):
    foreign = CaseContext("FR", "import", "consumption", "sea", ctx.declaration_date)
    with pytest.raises(UnresolvedRegulatoryCondition):
        evaluate_requirements(foreign, [rule()])


def test_required_transport_unknown_fails_closed(ctx):
    missing = CaseContext("GA", "import", "consumption", "", ctx.declaration_date)
    with pytest.raises(UnresolvedRegulatoryCondition):
        evaluate_requirements(missing, [rule(transport_mode="sea")])
