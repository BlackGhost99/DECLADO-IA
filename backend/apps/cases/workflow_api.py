"""HTTP endpoints for preparatory workflow transitions."""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError
from apps.organizations.business_permissions import has_feature
from apps.organizations.permissions import HasActiveOrganization

from .workflow_service import transition_revision


class WorkflowTransitionInput(serializers.Serializer):
    target = serializers.ChoiceField(choices=[
        "in_preparation", "to_validate", "to_correct", "validated",
    ])
    row_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class WorkflowTransitionView(APIView):
    permission_classes = [HasActiveOrganization]

    def post(self, request, revision_id):
        if not has_feature(request.user, request.organization, "cases"):
            raise ApiError("FEATURE_DENIED", "Gestion de dossiers non autorisée.", 403)
        data = WorkflowTransitionInput(data=request.data)
        data.is_valid(raise_exception=True)
        revision = transition_revision(
            organization=request.organization,
            actor=request.user,
            revision_id=revision_id,
            expected_version=data.validated_data["row_version"],
            target=data.validated_data["target"],
            reason=data.validated_data.get("reason", ""),
        )
        return Response({
            "revision_id": str(revision.pk),
            "state": revision.state,
            "row_version": revision.row_version,
        })
