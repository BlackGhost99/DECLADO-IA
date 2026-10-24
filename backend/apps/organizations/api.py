from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError, RevisionConflict

from . import services
from .models import Membership, Role
from .permissions import require_roles

IsOrgAdmin = require_roles(Role.ORG_ADMIN)


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    agency_name = serializers.CharField(source="agency.name", read_only=True, default=None)

    class Meta:
        model = Membership
        fields = [
            "id",
            "email",
            "full_name",
            "roles",
            "agency",
            "agency_name",
            "active",
            "deactivated_at",
            "row_version",
        ]


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    roles = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    initial_password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class RolesSerializer(serializers.Serializer):
    roles = serializers.ListField(child=serializers.CharField())
    row_version = serializers.IntegerField()


def _get_member(request, member_id) -> Membership:
    membership = (
        Membership.objects.select_related("user", "organization")
        .filter(organization=request.organization, pk=member_id)
        .first()
    )
    if membership is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return membership


class MemberListView(ListAPIView):
    permission_classes = [IsOrgAdmin]
    serializer_class = MemberSerializer

    def get_queryset(self):
        return (
            Membership.objects.select_related("user", "agency")
            .filter(organization=self.request.organization)
            .order_by("user__email")
        )

    def post(self, request):
        data = AddMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = services.add_member(
            organization=request.organization,
            actor=request.user,
            email=data.validated_data["email"],
            full_name=data.validated_data["full_name"],
            roles=data.validated_data["roles"],
            initial_password=data.validated_data.get("initial_password") or None,
        )
        return Response(MemberSerializer(membership).data, status=201)


class MemberRolesView(APIView):
    permission_classes = [IsOrgAdmin]

    def put(self, request, member_id):
        data = RolesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = _get_member(request, member_id)
        if membership.row_version != data.validated_data["row_version"]:
            raise RevisionConflict(data.validated_data["row_version"], membership.row_version)
        services.set_roles(membership=membership, actor=request.user, roles=data.validated_data["roles"])
        return Response(MemberSerializer(membership).data)


class MemberDeactivateView(APIView):
    permission_classes = [IsOrgAdmin]

    def post(self, request, member_id):
        membership = services.deactivate_member(membership=_get_member(request, member_id), actor=request.user)
        return Response(MemberSerializer(membership).data)
