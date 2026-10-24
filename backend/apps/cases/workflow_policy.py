"""Restricted preparatory transitions; final validation is deliberately excluded."""
from dataclasses import dataclass
from apps.organizations.models import Role


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    roles: frozenset[str]
    reason_required: bool = False


TRANSITIONS = (
    Transition("draft", "in_preparation", frozenset({Role.DECLARANT, Role.VALIDATOR})),
    Transition("in_preparation", "to_validate", frozenset({Role.DECLARANT, Role.VALIDATOR})),
    Transition("to_correct", "to_validate", frozenset({Role.DECLARANT, Role.VALIDATOR})),
    Transition("to_validate", "to_correct", frozenset({Role.VALIDATOR}), True),
)


def allowed_transition(source, target, roles, reason=""):
    return any(
        rule.source == source and rule.target == target
        and bool(rule.roles.intersection(roles))
        and (not rule.reason_required or bool(reason.strip()))
        for rule in TRANSITIONS
    )
