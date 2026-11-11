"""Régression : un calcul import provisoire ne peut pas être soumis en mode opérationnel."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.cases import workflow
from apps.cases.models import CaseRevision
from apps.core.exceptions import ApiError


@pytest.fixture
def submit_context(monkeypatch):
    revision = SimpleNamespace(id="revision-test", mode=CaseRevision.Mode.OPERATIONAL, is_editable=True)
    case = SimpleNamespace(current_revision=revision)
    lock = Mock(return_value=(case, revision))
    decide = Mock(return_value=object())
    monkeypatch.setattr(workflow, "_lock", lock)
    monkeypatch.setattr(workflow, "check_version", Mock())
    monkeypatch.setattr(workflow.completeness, "evaluate", Mock(return_value={"blocking": []}))
    monkeypatch.setattr(workflow, "_decide", decide)
    return case, revision, decide


@pytest.mark.django_db
def test_import_operational_provisional_total_is_blocked(monkeypatch, submit_context):
    _, _, decide = submit_context
    monkeypatch.setattr(
        workflow,
        "case_calculation",
        Mock(
            return_value={
                "totals": {"total": "12500"},
                "provisional": True,
                "provisional_reasons": ["Pièce de fret absente : valeur provisoire sans fret."],
            }
        ),
    )
    with pytest.raises(ApiError) as exc:
        workflow.submit(org=object(), actor=object(), case_id="case", expected=1)
    assert exc.value.status_code == 409
    assert exc.value.error_code == "SUBMISSION_BLOCKED"
    assert "fret" in exc.value.details["blocking"][0]["message"]
    decide.assert_not_called()


@pytest.mark.django_db
def test_import_operational_complete_total_is_submittable(monkeypatch, submit_context):
    _, _, decide = submit_context
    monkeypatch.setattr(
        workflow,
        "case_calculation",
        Mock(return_value={"totals": {"total": "12500"}, "provisional": False}),
    )
    workflow.submit(org=object(), actor=object(), case_id="case", expected=1)
    decide.assert_called_once()


@pytest.mark.django_db
def test_import_demo_provisional_is_not_blocked_by_operational_guard(monkeypatch, submit_context):
    _, revision, decide = submit_context
    revision.mode = CaseRevision.Mode.DEMO
    monkeypatch.setattr(
        workflow,
        "case_calculation",
        Mock(return_value={"totals": {"total": "12500"}, "provisional": True, "provisional_reasons": ["Fret absent."]}),
    )
    workflow.submit(org=object(), actor=object(), case_id="case", expected=1)
    decide.assert_called_once()
