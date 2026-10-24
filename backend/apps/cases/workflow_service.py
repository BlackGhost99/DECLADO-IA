"""Transactional, audited workflow changes scoped to an organization."""
from django.db import transaction
from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.context import active_memberships
from .models import CaseRevision
from .workflow_policy import allowed_transition


@transaction.atomic
def transition_revision(*, organization, actor, revision_id, expected_version, target, reason=""):
    membership = active_memberships(actor).filter(organization=organization).first()
    if membership is None:
        raise ApiError("FORBIDDEN", "Affiliation active requise.", 403)
    revision = (
        CaseRevision.objects.for_organization(organization)
        .select_for_update()
        .select_related("case")
        .filter(pk=revision_id)
        .first()
    )
    if revision is None:
        raise ApiError("NOT_FOUND", "Révision introuvable.", 404)
    if revision.case.current_revision_id != revision.pk:
        raise ApiError("STALE_REVISION", "Seule la révision courante est modifiable.", 409)
    if revision.row_version != expected_version:
        raise ApiError("REVISION_CONFLICT", "Version obsolète.", 409)
    if not allowed_transition(revision.state, target, membership.roles, reason):
        raise ApiError("TRANSITION_DENIED", "Transition interdite ou motif manquant.", 403)
    previous = revision.state
    revision.state = target
    revision.reason = reason.strip()
    revision.row_version += 1
    revision.save(update_fields=["state", "reason", "row_version", "updated_at"])
    record_event(
        organization=organization, actor=actor, event_type="revision.workflow_transition",
        entity=revision, previous={"state": previous},
        current={"state": target, "reason": revision.reason},
        scope=revision.case.scope,
    )
    return revision
