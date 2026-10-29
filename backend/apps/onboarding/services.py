"""Mise en route : premier compte exploitant, demandes d'espace, sociétés et invitations.

Toutes les opérations sont journalisées. Les jetons d'invitation ne sont rendus qu'une fois,
à leur création ; seule leur empreinte est conservée.
"""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record_event
from apps.core.exceptions import ApiError, RevisionConflict
from apps.organizations.business_models import OPEN_PROFILES, Agency, OrganizationBusinessProfile
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.services import _clean_roles

from .models import AccessRequest, Invitation

INVITATION_TTL = timedelta(hours=72)
# Pays de la CEMAC (ISO 3166-1 alpha-2).
CEMAC_COUNTRIES = frozenset({"GA", "CM", "CG", "CF", "GQ", "TD"})
LOCALES = frozenset({"fr", "en", "es", "ar"})
# Verrou applicatif : deux premiers lancements simultanés ne créent qu'un seul exploitant.
_SETUP_LOCK = 0x43540001


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _check_password(password: str, user: User | None = None) -> None:
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ApiError("WEAK_PASSWORD", "Mot de passe trop faible.", 400, {"errors": exc.messages}) from exc


def _check_profile(profile: str) -> None:
    if profile not in OPEN_PROFILES:
        raise ApiError("PROFILE_NOT_OPEN", "Ce métier n'est pas encore ouvert.", 400, {"profile": profile})


def _check_country(country_code: str) -> str:
    code = (country_code or "").upper()
    if code not in CEMAC_COUNTRIES:
        raise ApiError("COUNTRY_NOT_CEMAC", "Pays hors CEMAC.", 400, {"country_code": country_code})
    return code


# ---------- Premier lancement ----------


def needs_setup() -> bool:
    return not User.objects.exists()


@transaction.atomic
def create_operator(*, full_name: str, email: str, password: str) -> User:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SETUP_LOCK])
    if User.objects.exists():
        # Une fois le serveur mis en service, cet écran ne crée plus rien.
        raise ApiError("SETUP_DONE", "ClairTransit est déjà mis en service.", 409)
    _check_password(password, User(email=email, full_name=full_name))
    # L'exploitant publie aussi le référentiel commun (tarif, taxes) : il en est le gestionnaire.
    user = User.objects.create_user(
        email=email,
        password=password,
        full_name=full_name.strip(),
        is_platform_operator=True,
        is_reference_manager=True,
    )
    record_event(organization=None, actor=user, event_type="platform.setup", entity=user)
    return user


# ---------- Demandes d'ouverture ----------


@transaction.atomic
def submit_access_request(*, data: dict) -> AccessRequest:
    _check_profile(data["primary_profile"])
    country = _check_country(data["country_code"])
    locale = data.get("preferred_locale") or "fr"
    request = AccessRequest.objects.create(
        company_name=data["company_name"].strip(),
        primary_profile=data["primary_profile"],
        country_code=country,
        registration_number=data["registration_number"].strip(),
        contact_name=data["contact_name"].strip(),
        contact_role=(data.get("contact_role") or "").strip(),
        contact_email=data["contact_email"].strip().lower(),
        contact_phone=(data.get("contact_phone") or "").strip(),
        preferred_locale=locale if locale in LOCALES else "fr",
    )
    record_event(organization=None, actor=None, event_type="access_request.submitted", entity=request)
    return request


@transaction.atomic
def accept_access_request(*, access_request: AccessRequest, actor: User) -> tuple[Organization, Invitation, str]:
    access_request = AccessRequest.objects.select_for_update().get(pk=access_request.pk)
    if access_request.status != AccessRequest.Status.PENDING:
        raise ApiError("REQUEST_ALREADY_DECIDED", "Cette demande a déjà été traitée.", 409)
    organization, invitation, token = create_organization(
        actor=actor,
        name=access_request.company_name,
        primary_profile=access_request.primary_profile,
        country_code=access_request.country_code,
        default_locale=access_request.preferred_locale,
        max_users=None,
        admin_name=access_request.contact_name,
        admin_email=access_request.contact_email,
    )
    access_request.status = AccessRequest.Status.ACCEPTED
    access_request.decided_by = actor
    access_request.decided_at = timezone.now()
    access_request.organization = organization
    access_request.row_version += 1
    access_request.save()
    record_event(
        organization=None,
        actor=actor,
        event_type="access_request.accepted",
        entity=access_request,
        current={"organization": str(organization.pk)},
    )
    return organization, invitation, token


@transaction.atomic
def refuse_access_request(*, access_request: AccessRequest, actor: User, note: str) -> AccessRequest:
    access_request = AccessRequest.objects.select_for_update().get(pk=access_request.pk)
    if access_request.status != AccessRequest.Status.PENDING:
        raise ApiError("REQUEST_ALREADY_DECIDED", "Cette demande a déjà été traitée.", 409)
    access_request.status = AccessRequest.Status.REFUSED
    access_request.decided_by = actor
    access_request.decided_at = timezone.now()
    access_request.decision_note = (note or "").strip()[:500]
    access_request.row_version += 1
    access_request.save()
    record_event(organization=None, actor=actor, event_type="access_request.refused", entity=access_request)
    return access_request


# ---------- Sociétés (console) ----------


@transaction.atomic
def create_organization(
    *,
    actor: User,
    name: str,
    primary_profile: str,
    country_code: str,
    default_locale: str,
    max_users: int | None,
    admin_name: str,
    admin_email: str,
) -> tuple[Organization, Invitation, str]:
    _check_profile(primary_profile)
    country = _check_country(country_code)
    if default_locale not in LOCALES:
        raise ApiError("UNKNOWN_LOCALE", "Langue inconnue.", 400)
    if max_users is not None and max_users < 1:
        raise ApiError("INVALID_SEATS", "Le nombre d'utilisateurs doit être au moins 1.", 400)
    organization = Organization.objects.create(
        name=name.strip(), country_code=country, default_locale=default_locale, max_users=max_users
    )
    OrganizationBusinessProfile.objects.create(organization=organization, primary_profile=primary_profile)
    record_event(
        organization=organization,
        actor=actor,
        event_type="organization.created",
        entity=organization,
        current={"name": organization.name, "profile": primary_profile, "country": country},
    )
    invitation, token = invite(
        organization=organization,
        actor=actor,
        email=admin_email,
        full_name=admin_name,
        roles=[Role.ORG_ADMIN],
        agency=None,
    )
    return organization, invitation, token


@transaction.atomic
def set_organization_active(*, organization: Organization, actor: User, active: bool) -> Organization:
    """Une société suspendue garde ses données ; ses utilisateurs ne peuvent plus y entrer."""
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    previous = organization.active
    if previous == active:
        return organization
    organization.active = active
    organization.row_version += 1
    organization.save(update_fields=["active", "row_version", "updated_at"])
    record_event(
        organization=organization,
        actor=actor,
        event_type="organization.reactivated" if active else "organization.suspended",
        entity=organization,
        previous={"active": previous},
        current={"active": active},
    )
    return organization


@transaction.atomic
def update_organization_capacities(
    *,
    organization: Organization,
    actor: User,
    max_users: int | None,
    max_agencies: int | None,
    row_version: int,
    reason: str,
) -> Organization:
    """Seul l'exploitant fixe les capacités ; aucune donnée métier n'est lue ou renvoyée."""
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    if organization.row_version != row_version:
        raise RevisionConflict(row_version, organization.row_version)
    used = seats_used(organization)  # membres actifs ET invitations encore valides
    agencies = Agency.objects.for_organization(organization).filter(active=True).count()
    if max_users is not None and max_users < used:
        raise ApiError(
            "SEATS_IN_USE", "La limite ne peut pas être inférieure aux places utilisées.", 409, {"used": used}
        )
    if max_agencies is not None and max_agencies < agencies:
        raise ApiError(
            "AGENCIES_IN_USE", "La limite ne peut pas être inférieure aux agences actives.", 409, {"used": agencies}
        )
    previous = {"max_users": organization.max_users, "max_agencies": organization.max_agencies}
    current = {"max_users": max_users, "max_agencies": max_agencies}
    if previous == current:
        return organization
    organization.max_users = max_users
    organization.max_agencies = max_agencies
    organization.row_version += 1
    organization.save(update_fields=["max_users", "max_agencies", "row_version", "updated_at"])
    record_event(
        organization=organization,
        actor=actor,
        event_type="organization.capacities_changed",
        entity=organization,
        previous=previous,
        current={**current, "reason": reason},
        scope="platform",
    )
    return organization


# ---------- Invitations ----------


def seats_used(organization: Organization) -> int:
    members = Membership.objects.filter(organization=organization, active=True).count()
    pending = pending_invitations(organization).count()
    return members + pending


def pending_invitations(organization: Organization):
    return Invitation.objects.for_organization(organization).filter(
        accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()
    )


def check_seat(organization: Organization) -> None:
    if organization.max_users is not None and seats_used(organization) >= organization.max_users:
        raise ApiError(
            "SEAT_LIMIT",
            "Nombre d'utilisateurs prévu atteint.",
            409,
            {"max_users": organization.max_users},
        )


def _new_token() -> str:
    return secrets.token_urlsafe(32)


@transaction.atomic
def invite(
    *, organization: Organization, actor: User, email: str, full_name: str, roles, agency: Agency | None
) -> tuple[Invitation, str]:
    # Même verrou pour invitations, créations directes, réactivations et modifications de quota.
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    roles = _clean_roles(roles)
    if not roles:
        raise ApiError("ROLE_REQUIRED", "Choisissez au moins un rôle.", 400)
    email = email.strip().lower()
    if agency is not None and agency.organization_id != organization.pk:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    if Membership.objects.filter(organization=organization, user__email=email, active=True).exists():
        raise ApiError("ALREADY_MEMBER", "Cet utilisateur est déjà affilié à la société.", 409)
    # Une nouvelle invitation remplace la précédente pour la même adresse.
    now = timezone.now()
    pending_invitations(organization).filter(email=email).update(revoked_at=now)
    check_seat(organization)
    token = _new_token()
    invitation = Invitation.objects.create(
        organization=organization,
        email=email,
        full_name=full_name.strip(),
        roles=roles,
        agency=agency,
        token_hash=_hash(token),
        expires_at=now + INVITATION_TTL,
        created_by=actor,
    )
    record_event(
        organization=organization,
        actor=actor,
        event_type="invitation.created",
        entity=invitation,
        current={"email": email, "roles": roles},
    )
    return invitation, token


@transaction.atomic
def renew_invitation(*, invitation: Invitation, actor: User) -> tuple[Invitation, str]:
    if invitation.accepted_at:
        raise ApiError("INVITATION_USED", "Cette invitation a déjà été utilisée.", 409)
    if invitation.revoked_at:
        raise ApiError("INVITATION_REVOKED", "Cette invitation a été annulée.", 409)
    organization = Organization.objects.select_for_update().get(pk=invitation.organization_id)
    # Renouveler un lien expiré réserve de nouveau une place.
    if invitation.expires_at <= timezone.now():
        check_seat(organization)
    token = _new_token()
    invitation.token_hash = _hash(token)
    invitation.expires_at = timezone.now() + INVITATION_TTL
    invitation.row_version += 1
    invitation.save(update_fields=["token_hash", "expires_at", "row_version", "updated_at"])
    record_event(organization=invitation.organization, actor=actor, event_type="invitation.renewed", entity=invitation)
    return invitation, token


@transaction.atomic
def revoke_invitation(*, invitation: Invitation, actor: User) -> Invitation:
    if invitation.accepted_at:
        raise ApiError("INVITATION_USED", "Cette invitation a déjà été utilisée.", 409)
    if not invitation.revoked_at:
        invitation.revoked_at = timezone.now()
        invitation.row_version += 1
        invitation.save(update_fields=["revoked_at", "row_version", "updated_at"])
        record_event(
            organization=invitation.organization, actor=actor, event_type="invitation.revoked", entity=invitation
        )
    return invitation


def invitation_by_token(token: str, *, lock: bool = False) -> Invitation:
    """Lien inconnu, utilisé, annulé ou expiré : même réponse, sans rien révéler."""
    queryset = Invitation.objects.select_related("organization", "agency")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    invitation = queryset.filter(token_hash=_hash(token or "")).first()
    if (
        invitation is None
        or invitation.accepted_at
        or invitation.revoked_at
        or invitation.expires_at <= timezone.now()
        or not invitation.organization.active
    ):
        raise ApiError("INVITATION_INVALID", "Ce lien d'invitation n'est plus valable.", 404)
    return invitation


@transaction.atomic
def accept_invitation(*, token: str, full_name: str, password: str) -> tuple[User, Membership]:
    invitation = invitation_by_token(token, lock=True)
    user = User.objects.filter(email=invitation.email).first()
    if user is None:
        _check_password(password, User(email=invitation.email, full_name=full_name))
        user = User.objects.create_user(
            email=invitation.email,
            password=password,
            full_name=(full_name or invitation.full_name).strip(),
            interface_locale=invitation.organization.default_locale,
        )
    elif not user.is_active or not user.check_password(password):
        # Compte déjà existant : il rejoint la société avec son propre mot de passe, jamais un nouveau.
        raise ApiError("INVALID_CREDENTIALS", "Identifiants incorrects.", 400)
    membership = Membership.objects.filter(organization=invitation.organization, user=user).first()
    if membership is None:
        membership = Membership.objects.create(
            organization=invitation.organization, user=user, roles=invitation.roles, agency=invitation.agency
        )
    elif membership.active:
        raise ApiError("ALREADY_MEMBER", "Cet utilisateur est déjà affilié à la société.", 409)
    else:
        membership.active = True
        membership.deactivated_at = None
        membership.roles = invitation.roles
        membership.agency = invitation.agency
        membership.row_version += 1
        membership.save()
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.row_version += 1
    invitation.save(update_fields=["accepted_at", "accepted_by", "row_version", "updated_at"])
    record_event(
        organization=invitation.organization,
        actor=user,
        event_type="invitation.accepted",
        entity=membership,
        current={"user": user.email, "roles": membership.roles},
    )
    return user, membership


# ---------- Agences ----------


@transaction.atomic
def create_agency(*, organization: Organization, actor: User, name: str, code: str) -> Agency:
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    active_agencies = Agency.objects.for_organization(organization).filter(active=True).count()
    if organization.max_agencies is not None and active_agencies >= organization.max_agencies:
        raise ApiError("AGENCY_LIMIT", "Nombre d\u0027agences autorisé atteint.", 409)
    code = code.strip().upper()
    if Agency.objects.for_organization(organization).filter(code=code).exists():
        raise ApiError("AGENCY_EXISTS", "Une agence porte déjà ce code.", 409)
    agency = Agency.objects.create(
        organization=organization, name=name.strip(), code=code, country_code=organization.country_code
    )
    record_event(
        organization=organization,
        actor=actor,
        event_type="agency.created",
        entity=agency,
        current={"name": agency.name, "code": code},
    )
    return agency


@transaction.atomic
def set_member_agency(*, membership: Membership, actor: User, agency: Agency | None) -> Membership:
    if agency is not None and agency.organization_id != membership.organization_id:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    previous = str(membership.agency_id) if membership.agency_id else None
    membership.agency = agency
    membership.row_version += 1
    membership.save(update_fields=["agency", "row_version", "updated_at"])
    record_event(
        organization=membership.organization,
        actor=actor,
        event_type="membership.agency_changed",
        entity=membership,
        previous={"agency": previous},
        current={"agency": str(agency.pk) if agency else None},
    )
    return membership


@transaction.atomic
def reactivate_member(*, membership: Membership, actor: User) -> Membership:
    if membership.active:
        return membership
    organization = Organization.objects.select_for_update().get(pk=membership.organization_id)
    check_seat(organization)
    membership.active = True
    membership.deactivated_at = None
    membership.row_version += 1
    membership.save(update_fields=["active", "deactivated_at", "row_version", "updated_at"])
    record_event(
        organization=membership.organization,
        actor=actor,
        event_type="membership.reactivated",
        entity=membership,
        previous={"active": False},
        current={"active": True},
    )
    return membership
