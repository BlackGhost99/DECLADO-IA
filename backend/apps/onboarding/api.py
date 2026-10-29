"""API de mise en route.

- `auth/setup`, `auth/access-requests`, `auth/invitations/*` : publics, protégés CSRF et limités en débit ;
- `platform/*` : console de l'exploitant (aucun accès aux dossiers des sociétés) ;
- `organization/invitations`, `organization/agencies` : administrateur de la société active.
"""

from django.contrib.auth import login
from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import me_payload
from apps.accounts.mfa import rate_limit
from apps.accounts.models import TotpDevice
from apps.audit.models import AuditEvent
from apps.core.exceptions import ApiError
from apps.organizations.business_models import Agency, BusinessProfile
from apps.organizations.context import set_active_organization
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.permissions import require_roles

from . import services
from .mail import app_url, send_invitation_email
from .models import AccessRequest, Invitation

IsOrgAdmin = require_roles(Role.ORG_ADMIN)


class IsPlatformOperator(BasePermission):
    """Console ClairTransit : réservée à l'exploitant, jamais ouverte par une affiliation."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_platform_operator)


# ---------- Sérialiseurs ----------


class SetupInput(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, max_length=200)


class AccessRequestInput(serializers.Serializer):
    company_name = serializers.CharField(max_length=200)
    primary_profile = serializers.ChoiceField(choices=BusinessProfile.choices)
    country_code = serializers.CharField(max_length=2)
    registration_number = serializers.CharField(max_length=80)
    contact_name = serializers.CharField(max_length=200)
    contact_role = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    contact_email = serializers.EmailField()
    contact_phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    preferred_locale = serializers.CharField(max_length=2, required=False, default="fr")


class AccessRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessRequest
        fields = [
            "id",
            "company_name",
            "primary_profile",
            "country_code",
            "registration_number",
            "contact_name",
            "contact_role",
            "contact_email",
            "contact_phone",
            "status",
            "created_at",
            "decided_at",
            "decision_note",
            "organization",
        ]


class TokenInput(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class AcceptInput(TokenInput):
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    password = serializers.CharField(trim_whitespace=False, max_length=200)


class OrganizationInput(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    primary_profile = serializers.ChoiceField(choices=BusinessProfile.choices)
    country_code = serializers.CharField(max_length=2)
    default_locale = serializers.CharField(max_length=2, default="fr")
    max_users = serializers.IntegerField(required=False, allow_null=True, default=None)
    admin_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()


class PlatformCapacitiesInput(serializers.Serializer):
    max_users = serializers.IntegerField(min_value=1, required=True, allow_null=True)
    max_agencies = serializers.IntegerField(min_value=1, required=True, allow_null=True)
    row_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=8, max_length=500, trim_whitespace=True)


class RefuseInput(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class InvitationInput(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    roles = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    agency_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class InvitationSerializer(serializers.ModelSerializer):
    agency_name = serializers.CharField(source="agency.name", read_only=True, default=None)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ["id", "email", "full_name", "roles", "agency", "agency_name", "expires_at", "created_at", "status"]

    def get_status(self, obj) -> str:
        from django.utils import timezone

        if obj.accepted_at:
            return "accepted"
        if obj.revoked_at:
            return "revoked"
        return "expired" if obj.expires_at <= timezone.now() else "pending"


class AgencyInput(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=40)


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ["id", "name", "code", "country_code", "active"]


class MemberAgencyInput(serializers.Serializer):
    agency_id = serializers.UUIDField(allow_null=True)


def _with_token(request, invitation: Invitation, token: str) -> dict:
    # Le jeton n'est rendu qu'ici, une seule fois : l'interface en fait le lien à copier,
    # et l'envoie aussi par e-mail quand un serveur SMTP est configuré.
    email = send_invitation_email(invitation=invitation, token=token, base_url=app_url(request), actor=request.user)
    return {**InvitationSerializer(invitation).data, "token": token, "email_status": email}


# ---------- Public ----------


@method_decorator(csrf_protect, name="dispatch")
class SetupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"needs_setup": services.needs_setup()})

    def post(self, request):
        rate_limit(request, "platform-setup", "-", limit=10, seconds=300)
        data = SetupInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.create_operator(**data.validated_data)
        login(request, user)
        return Response(me_payload(request), status=201)


@method_decorator(csrf_protect, name="dispatch")
class PublicAccessRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        rate_limit(request, "access-request", "-", limit=5, seconds=3600)
        data = AccessRequestInput(data=request.data)
        data.is_valid(raise_exception=True)
        services.submit_access_request(data=data.validated_data)
        # Aucune information en retour : l'exploitant répond après vérification.
        return Response({"received": True}, status=201)


@method_decorator(csrf_protect, name="dispatch")
class InvitationLookupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        rate_limit(request, "invitation-lookup", "-", limit=30, seconds=300)
        data = TokenInput(data=request.data)
        data.is_valid(raise_exception=True)
        invitation = services.invitation_by_token(data.validated_data["token"])
        from apps.accounts.models import User

        return Response(
            {
                "organization_name": invitation.organization.name,
                "email": invitation.email,
                "full_name": invitation.full_name,
                "roles": invitation.roles,
                "agency_name": invitation.agency.name if invitation.agency else None,
                "expires_at": invitation.expires_at,
                "existing_account": User.objects.filter(email=invitation.email).exists(),
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class InvitationAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = AcceptInput(data=request.data)
        data.is_valid(raise_exception=True)
        rate_limit(request, "invitation-accept", data.validated_data["token"][:16], limit=8, seconds=300)
        user, membership = services.accept_invitation(**data.validated_data)
        request.session.flush()
        login(request, user)
        set_active_organization(request, membership.organization_id)
        return Response(me_payload(request))


# ---------- Console de l'exploitant ----------


class PlatformAccessRequestListView(APIView):
    permission_classes = [IsPlatformOperator]

    def get(self, request):
        queryset = AccessRequest.objects.all()
        state = request.query_params.get("status")
        if state:
            queryset = queryset.filter(status=state)
        return Response(AccessRequestSerializer(queryset[:200], many=True).data)


def _access_request(pk) -> AccessRequest:
    item = AccessRequest.objects.filter(pk=pk).first()
    if item is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return item


class PlatformAccessRequestAcceptView(APIView):
    permission_classes = [IsPlatformOperator]

    def post(self, request, request_id):
        organization, invitation, token = services.accept_access_request(
            access_request=_access_request(request_id), actor=request.user
        )
        return Response(
            {"organization_id": str(organization.pk), "invitation": _with_token(request, invitation, token)}, status=201
        )


class PlatformAccessRequestRefuseView(APIView):
    permission_classes = [IsPlatformOperator]

    def post(self, request, request_id):
        data = RefuseInput(data=request.data)
        data.is_valid(raise_exception=True)
        item = services.refuse_access_request(
            access_request=_access_request(request_id), actor=request.user, note=data.validated_data["note"]
        )
        return Response(AccessRequestSerializer(item).data)


def _organization_rows(organization_id=None):
    organizations = (
        Organization.objects.select_related("business_profile")
        .annotate(
            members=Count("memberships", filter=Q(memberships__active=True), distinct=True),
            agencies_count=Count("agencies", filter=Q(agencies__active=True), distinct=True),
        )
        .order_by("name")
    )
    if organization_id is not None:
        organizations = organizations.filter(pk=organization_id)
    pending = services.pending_invitations
    rows = []
    for org in organizations:
        # Dernière invitation d'administrateur non utilisée, même expirée : l'exploitant peut la renouveler.
        admin_invite = (
            Invitation.objects.for_organization(org)
            .filter(roles__contains=[Role.ORG_ADMIN], accepted_at__isnull=True, revoked_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        profile = getattr(org, "business_profile", None)
        rows.append(
            {
                "id": str(org.pk),
                "name": org.name,
                "primary_profile": profile.primary_profile if profile else BusinessProfile.TRANSIT,
                "country_code": org.country_code,
                "default_locale": org.default_locale,
                "active": org.active,
                "is_demo": org.is_demo,
                "max_users": org.max_users,
                "max_agencies": org.max_agencies,
                "row_version": org.row_version,
                "members": org.members,
                "agencies": org.agencies_count,
                "pending_invitations": pending(org).count(),
                "admin_invitation": InvitationSerializer(admin_invite).data if admin_invite else None,
                "created_at": org.created_at,
            }
        )
    return rows


_PLATFORM_AUDIT_EVENTS = (
    "organization.created",
    "organization.suspended",
    "organization.reactivated",
    "organization.capacities_changed",
)


def _organization_detail(organization: Organization):
    result = _organization_rows(organization.pk)[0]
    admins = (
        Membership.objects.filter(organization=organization, roles__contains=[Role.ORG_ADMIN])
        .select_related("user")
        .order_by("user__email")
    )
    enabled_mfa = set(
        TotpDevice.objects.filter(
            user_id__in=[member.user_id for member in admins], confirmed_at__isnull=False
        ).values_list("user_id", flat=True)
    )
    result["administrators"] = [
        {
            "full_name": member.user.full_name,
            "email": member.user.email,
            "active": member.active and member.user.is_active,
            "mfa_enabled": member.user_id in enabled_mfa,
        }
        for member in admins
    ]
    events = (
        AuditEvent.objects.filter(organization=organization, event_type__in=_PLATFORM_AUDIT_EVENTS)
        .select_related("actor")
        .order_by("-at")[:30]
    )
    result["history"] = [
        {
            "id": str(event.pk),
            "at": event.at,
            "event_type": event.event_type,
            "actor": event.actor.full_name if event.actor else None,
            "previous": event.previous,
            "current": event.current,
        }
        for event in events
    ]
    return result


class PlatformOrganizationListView(APIView):
    permission_classes = [IsPlatformOperator]

    def get(self, request):
        return Response(_organization_rows())

    def post(self, request):
        data = OrganizationInput(data=request.data)
        data.is_valid(raise_exception=True)
        organization, invitation, token = services.create_organization(actor=request.user, **data.validated_data)
        return Response(
            {"organization_id": str(organization.pk), "invitation": _with_token(request, invitation, token)}, status=201
        )


def _organization(pk) -> Organization:
    org = Organization.objects.filter(pk=pk).first()
    if org is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return org


class PlatformOrganizationDetailView(APIView):
    permission_classes = [IsPlatformOperator]

    def get(self, request, organization_id):
        return Response(_organization_detail(_organization(organization_id)))

    def patch(self, request, organization_id):
        data = PlatformCapacitiesInput(data=request.data)
        data.is_valid(raise_exception=True)
        updated = services.update_organization_capacities(
            organization=_organization(organization_id), actor=request.user, **data.validated_data
        )
        return Response(_organization_detail(updated))


class PlatformOrganizationStateView(APIView):
    permission_classes = [IsPlatformOperator]

    def post(self, request, organization_id, action):
        if action not in ("suspend", "reactivate"):
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        services.set_organization_active(
            organization=_organization(organization_id), actor=request.user, active=action == "reactivate"
        )
        return Response({"active": action == "reactivate"})


class PlatformInvitationRenewView(APIView):
    """L'exploitant ne renouvelle que les invitations d'administrateur, pour débloquer une mise en route."""

    permission_classes = [IsPlatformOperator]

    def post(self, request, invitation_id):
        invitation = (
            Invitation.objects.select_related("organization")
            .filter(pk=invitation_id, roles__contains=[Role.ORG_ADMIN])
            .first()
        )
        if invitation is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        invitation, token = services.renew_invitation(invitation=invitation, actor=request.user)
        return Response(_with_token(request, invitation, token))


# ---------- Administrateur de société ----------


def _agency(request, agency_id) -> Agency | None:
    if agency_id is None:
        return None
    agency = Agency.objects.for_organization(request.organization).filter(pk=agency_id, active=True).first()
    if agency is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return agency


class InvitationListView(APIView):
    permission_classes = [IsOrgAdmin]

    def get(self, request):
        queryset = Invitation.objects.for_organization(request.organization).select_related("agency")
        queryset = queryset.filter(accepted_at__isnull=True, revoked_at__isnull=True)
        return Response(InvitationSerializer(queryset[:200], many=True).data)

    def post(self, request):
        data = InvitationInput(data=request.data)
        data.is_valid(raise_exception=True)
        invitation, token = services.invite(
            organization=request.organization,
            actor=request.user,
            email=data.validated_data["email"],
            full_name=data.validated_data["full_name"],
            roles=data.validated_data["roles"],
            agency=_agency(request, data.validated_data["agency_id"]),
        )
        return Response(_with_token(request, invitation, token), status=201)


def _invitation(request, invitation_id) -> Invitation:
    invitation = Invitation.objects.for_organization(request.organization).filter(pk=invitation_id).first()
    if invitation is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return invitation


class InvitationActionView(APIView):
    permission_classes = [IsOrgAdmin]

    def post(self, request, invitation_id, action):
        invitation = _invitation(request, invitation_id)
        if action == "renew":
            invitation, token = services.renew_invitation(invitation=invitation, actor=request.user)
            return Response(_with_token(request, invitation, token))
        if action == "revoke":
            return Response(
                InvitationSerializer(services.revoke_invitation(invitation=invitation, actor=request.user)).data
            )
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)


class AgencyListView(APIView):
    def get_permissions(self):
        # Lecture ouverte aux membres (choix d'agence), création réservée à l'administrateur.
        return [require_roles(Role.ORG_ADMIN, safe_methods_open=True)()]

    def get(self, request):
        return Response(AgencySerializer(Agency.objects.for_organization(request.organization), many=True).data)

    def post(self, request):
        data = AgencyInput(data=request.data)
        data.is_valid(raise_exception=True)
        agency = services.create_agency(organization=request.organization, actor=request.user, **data.validated_data)
        return Response(AgencySerializer(agency).data, status=201)


def _member(request, member_id) -> Membership:
    membership = Membership.objects.filter(organization=request.organization, pk=member_id).first()
    if membership is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return membership


class MemberReactivateView(APIView):
    permission_classes = [IsOrgAdmin]

    def post(self, request, member_id):
        from apps.organizations.api import MemberSerializer

        membership = services.reactivate_member(membership=_member(request, member_id), actor=request.user)
        return Response(MemberSerializer(membership).data)


class MemberAgencyView(APIView):
    permission_classes = [IsOrgAdmin]

    def put(self, request, member_id):
        from apps.organizations.api import MemberSerializer

        data = MemberAgencyInput(data=request.data)
        data.is_valid(raise_exception=True)
        membership = services.set_member_agency(
            membership=_member(request, member_id),
            actor=request.user,
            agency=_agency(request, data.validated_data["agency_id"]),
        )
        return Response(MemberSerializer(membership).data)


class OrganizationOverviewView(APIView):
    """Mise en route de la société : ce qui est fait et ce qui reste (agences, équipe, circuit)."""

    permission_classes = [IsOrgAdmin]

    def get(self, request):
        org = request.organization
        profile = getattr(org, "business_profile", None)
        return Response(
            {
                "name": org.name,
                "primary_profile": profile.primary_profile if profile else BusinessProfile.TRANSIT,
                "country_code": org.country_code,
                "default_locale": org.default_locale,
                "max_users": org.max_users,
                "seats_used": services.seats_used(org),
                "members": Membership.objects.filter(organization=org, active=True).count(),
                "pending_invitations": services.pending_invitations(org).count(),
                "agencies": Agency.objects.for_organization(org).filter(active=True).count(),
                "validation_policy": org.validation_policy,
            }
        )
