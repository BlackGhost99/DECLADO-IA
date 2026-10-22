"""Résolution de la société active d'une requête.

La société active est dérivée de la session et d'une affiliation active ; un
identifiant de société envoyé par le client ne confère jamais de droit.
"""

from .models import Membership

SESSION_KEY = "active_organization_id"


def active_memberships(user):
    if not user or not user.is_authenticated or not user.is_active:
        return Membership.objects.none()
    return Membership.objects.select_related("organization").filter(user=user, active=True, organization__active=True)


def resolve_membership(request) -> Membership | None:
    cached = getattr(request, "_ct_membership", False)
    if cached is not False:
        return cached
    membership = None
    org_id = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if org_id:
        membership = active_memberships(request.user).filter(organization_id=org_id).first()
    request._ct_membership = membership
    return membership


def set_active_organization(request, organization_id) -> Membership | None:
    membership = active_memberships(request.user).filter(organization_id=organization_id).first()
    if membership is None:
        return None
    request.session[SESSION_KEY] = str(membership.organization_id)
    request._ct_membership = membership
    return membership


def auto_select_single_organization(request) -> Membership | None:
    memberships = list(active_memberships(request.user)[:2])
    if len(memberships) == 1:
        return set_active_organization(request, memberships[0].organization_id)
    return None
