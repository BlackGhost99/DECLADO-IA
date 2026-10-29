"""Opérations sur les affiliations, avec journalisation."""

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record_event
from apps.core.exceptions import ApiError

from .models import Membership, Organization, Role

VALID_ROLES = {r.value for r in Role}


def _clean_roles(roles) -> list[str]:
    roles = list(dict.fromkeys(roles or []))
    unknown = [r for r in roles if r not in VALID_ROLES]
    if unknown:
        raise ApiError("UNKNOWN_ROLE", "Rôle inconnu.", 400, {"roles": unknown})
    return roles


@transaction.atomic
def add_member(
    *, organization: Organization, actor: User, email: str, full_name: str, roles, initial_password: str | None
) -> Membership:
    # Empêche de contourner la capacité via l\u0027ancien endpoint de création directe.
    Organization.objects.select_for_update().get(pk=organization.pk)
    from apps.onboarding.services import check_seat

    check_seat(organization)
    roles = _clean_roles(roles)
    email = email.strip().lower()
    user = User.objects.filter(email=email).first()
    if user is None:
        if not initial_password:
            raise ApiError("PASSWORD_REQUIRED", "Mot de passe initial requis pour un nouveau compte.", 400)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(initial_password)
        except ValidationError as exc:
            raise ApiError("WEAK_PASSWORD", "Mot de passe trop faible.", 400, {"errors": exc.messages}) from exc
        user = User.objects.create_user(email=email, password=initial_password, full_name=full_name)
    membership, created = Membership.objects.get_or_create(
        organization=organization, user=user, defaults={"roles": roles}
    )
    if not created:
        raise ApiError("ALREADY_MEMBER", "Cet utilisateur est déjà affilié à la société.", 409)
    record_event(
        organization=organization,
        actor=actor,
        event_type="membership.created",
        entity=membership,
        current={"user": user.email, "roles": roles},
    )
    return membership


@transaction.atomic
def set_roles(*, membership: Membership, actor: User, roles) -> Membership:
    roles = _clean_roles(roles)
    previous = list(membership.roles)
    _guard_last_admin(membership, removing_admin=Role.ORG_ADMIN not in roles)
    membership.roles = roles
    membership.row_version += 1
    membership.save(update_fields=["roles", "row_version", "updated_at"])
    record_event(
        organization=membership.organization,
        actor=actor,
        event_type="membership.roles_changed",
        entity=membership,
        previous={"roles": previous},
        current={"roles": roles},
    )
    return membership


@transaction.atomic
def deactivate_member(*, membership: Membership, actor: User) -> Membership:
    """ACC-03 : l'accès est coupé immédiatement, l'historique reste attribué."""
    if membership.user_id == actor.id:
        raise ApiError("SELF_DEACTIVATION", "Vous ne pouvez pas désactiver votre propre accès.", 409)
    _guard_last_admin(membership, removing_admin=True)
    membership.active = False
    membership.deactivated_at = timezone.now()
    membership.row_version += 1
    membership.save(update_fields=["active", "deactivated_at", "row_version", "updated_at"])
    record_event(
        organization=membership.organization,
        actor=actor,
        event_type="membership.deactivated",
        entity=membership,
        previous={"active": True},
        current={"active": False},
    )
    return membership


@transaction.atomic
def deactivate_user(*, user: User, actor: User | None) -> User:
    """Désactivation globale (administration plateforme) : toutes les sessions deviennent invalides."""
    user.is_active = False
    user.deactivated_at = timezone.now()
    user.save(update_fields=["is_active", "deactivated_at"])
    record_event(
        organization=None,
        actor=actor,
        event_type="user.deactivated",
        entity=user,
        previous={"is_active": True},
        current={"is_active": False},
    )
    return user


def _guard_last_admin(membership: Membership, *, removing_admin: bool) -> None:
    if not removing_admin or Role.ORG_ADMIN not in membership.roles:
        return
    others = Membership.objects.filter(
        organization_id=membership.organization_id, active=True, roles__contains=[Role.ORG_ADMIN]
    ).exclude(pk=membership.pk)
    if not others.exists():
        raise ApiError("LAST_ADMIN", "La société doit conserver au moins un administrateur actif.", 409)
