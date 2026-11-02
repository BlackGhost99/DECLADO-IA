"""API du partage de dossiers (COL-01 à COL-07).

Côté propriétaire : `cases/{id}/shares`, `shares/{id}/revoke`. Côté partenaire : `shares/incoming`,
`shares/{id}/accept|refuse`. Les deux : `shares/{id}` (instantané pour le partenaire) et
`shares/{id}/notes`. Un partage n'ouvre jamais les écrans de travail du dossier au partenaire.
"""

from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.api import get_case
from apps.core.exceptions import ApiError
from apps.organizations.models import Role
from apps.organizations.permissions import HasActiveOrganization, require_roles

from . import services
from .models import CaseShare

CanShare = require_roles(Role.DECLARANT, Role.VALIDATOR, Role.ORG_ADMIN, safe_methods_open=True)
CanDecide = require_roles(Role.VALIDATOR, Role.ORG_ADMIN)
IsOrgAdmin = require_roles(Role.ORG_ADMIN, safe_methods_open=True)


class ShareInput(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    level = serializers.ChoiceField(choices=CaseShare.Level.choices)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class NoteInput(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


def _related():
    return CaseShare.objects.select_related("case", "organization", "partner", "created_by")


def _share_for(request, share_id, *, side: str) -> CaseShare:
    """`side` : owner, partner ou any. Une société tierce reçoit 404, jamais 403."""
    org = request.organization
    scope = {"owner": Q(organization=org), "partner": Q(partner=org), "any": Q(organization=org) | Q(partner=org)}
    share = _related().filter(scope[side], pk=share_id).first()
    if share is None:
        raise ApiError(*services.NOT_FOUND)
    return share


class PartnerCodeView(APIView):
    """COL-01 : code lu par tout membre pour le donner à un partenaire ; seul l'administrateur le renouvelle."""

    permission_classes = [IsOrgAdmin]

    def get(self, request):
        return Response({"code": services.partner_code(request.organization).code})

    def post(self, request):
        return Response({"code": services.regenerate_code(organization=request.organization, actor=request.user).code})


class CaseSharesView(APIView):
    permission_classes = [CanShare]

    def get(self, request, case_id):
        case = get_case(request, case_id)
        rows = _related().filter(organization=request.organization, case=case)
        return Response({"results": [services.share_payload(s, request.organization) for s in rows]})

    def post(self, request, case_id):
        case = get_case(request, case_id)
        data = ShareInput(data=request.data)
        data.is_valid(raise_exception=True)
        share = services.create_share(organization=request.organization, actor=request.user, case=case,
                                      **data.validated_data)  # fmt: skip
        return Response(services.share_payload(share, request.organization), status=201)


class ShareRevokeView(APIView):
    permission_classes = [CanShare]

    def post(self, request, share_id):
        share = services.revoke_share(share=_share_for(request, share_id, side="owner"), actor=request.user,
                                      reason=str(request.data.get("reason", "")))  # fmt: skip
        return Response(services.share_payload(share, request.organization))


class IncomingSharesView(APIView):
    """COL-03 : dossiers que d'autres sociétés partagent avec la société active."""

    permission_classes = [HasActiveOrganization]

    def get(self, request):
        rows = _related().filter(partner=request.organization).exclude(status=CaseShare.Status.REVOKED)
        return Response({"results": [services.share_payload(s, request.organization) for s in rows]})


class ShareDecisionView(APIView):
    permission_classes = [CanDecide]

    def post(self, request, share_id, action):
        if action not in ("accept", "refuse"):
            raise ApiError(*services.NOT_FOUND)
        share = services.decide_share(share=_share_for(request, share_id, side="partner"), actor=request.user,
                                      accept=action == "accept")  # fmt: skip
        return Response(services.share_payload(share, request.organization))


class ShareDetailView(APIView):
    """COL-06 : le partenaire lit l'instantané d'un partage accepté ; chaque lecture est journalisée."""

    permission_classes = [HasActiveOrganization]

    def get(self, request, share_id):
        share = _share_for(request, share_id, side="any")
        org = request.organization
        body = {"share": services.share_payload(share, org)}
        partner_side = share.partner_id == org.pk
        if partner_side and not share.is_open:
            raise ApiError("SHARE_CLOSED", "Ce partage n'est pas ouvert.", 409)
        if partner_side:
            services.record_view(share=share, actor=request.user)
            body["case"] = services.snapshot(share)
        body["notes"] = services.notes_payload(share, org)
        return Response(body)


class ShareNotesView(APIView):
    permission_classes = [HasActiveOrganization]

    def post(self, request, share_id):
        share = _share_for(request, share_id, side="any")
        data = NoteInput(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_note(share=share, organization=request.organization, actor=request.user,
                          text=data.validated_data["text"])  # fmt: skip
        return Response({"notes": services.notes_payload(share, request.organization)}, status=201)
