import pytest
from types import SimpleNamespace
from apps.core.exceptions import ApiError
from apps.cases.validation_policy import can_validate, policy_for


class Member:
    def __init__(self, roles):
        self.roles = roles

    def has_role(self, *roles):
        return any(role in self.roles for role in roles)


def build(mode, roles, *, warning=False, complete=True, same_agent=True):
    user = SimpleNamespace(pk="a")
    case = SimpleNamespace(
        assigned_to_id="a" if same_agent else "b",
        created_by_id="a" if same_agent else "b",
    )
    revision = SimpleNamespace(case=case, mode="operational")
    org = SimpleNamespace(validation_policy={"mode": mode})
    assessment = {"complete": complete, "blocking": [] if complete else ["missing"], "warnings": ["check"] if warning else []}
    return dict(organization=org, membership=Member(roles), actor=user, revision=revision, assessment=assessment)


def test_legacy_policy_defaults_to_two_people():
    assert policy_for(SimpleNamespace(validation_policy={"version": 1, "require_distinct_validator": True}))["mode"] == "dual_control"


def test_single_agent_may_validate_own_complete_case():
    assert can_validate(**build("single_agent", ["declarant"]))["dual_control_applied"] is False


def test_dual_control_denies_preparer():
    with pytest.raises(ApiError):
        can_validate(**build("dual_control", ["validator"]))


def test_dual_control_allows_independent_validator():
    assert can_validate(**build("dual_control", ["validator"], same_agent=False))["dual_control_applied"]


def test_conditional_requires_second_person_for_warning():
    with pytest.raises(ApiError):
        can_validate(**build("conditional", ["declarant"], warning=True))


def test_conditional_allows_agent_without_warning():
    assert not can_validate(**build("conditional", ["declarant"]))["dual_control_applied"]


def test_incomplete_case_never_passes():
    with pytest.raises(ApiError):
        can_validate(**build("single_agent", ["declarant"], complete=False))


def test_nonoperational_case_never_passes():
    args = build("single_agent", ["declarant"])
    args["revision"].mode = "historical"
    with pytest.raises(ApiError):
        can_validate(**args)
