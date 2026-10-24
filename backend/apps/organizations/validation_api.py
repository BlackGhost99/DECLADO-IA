"""Organization admin policy: explicit opt-in to single-agent validation."""
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from .models import Role
from .permissions import require_roles

MODES = ["single_agent", "dual_control", "conditional"]


class PolicyInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=MODES)
    row_version = serializers.IntegerField(min_value=1)


class ValidationPolicyView(APIView):
    permission_classes = [require_roles(Role.ORG_ADMIN)]

    def get(self, request):
        org = request.organization
        raw = org.validation_policy or {}
        return Response({
            "mode": raw.get("mode", "dual_control"),
            "row_version": org.row_version,
        })

    @transaction.atomic
    def put(self, request):
        from .models import Organization

        form = PolicyInput(data=request.data)
        form.is_valid(raise_exception=True)
        org = Organization.objects.select_for_update().get(pk=request.organization.pk, active=True)
        if org.row_version != form.validated_data["row_version"]:
            raise ApiError("REVISION_CONFLICT", "Version de configuration obsolète.", 409)
        old = org.validation_policy or {}
        new = {"version": int(old.get("version", 1)) + 1, "mode": form.validated_data["mode"]}
        org.validation_policy = new
        org.row_version += 1
        org.save(update_fields=["validation_policy", "row_version", "updated_at"])
        record_event(
            organization=org, actor=request.user, event_type="organization.validation_policy_changed",
            entity=org, previous=old, current=new,
        )
        return Response({"mode": new["mode"], "row_version": org.row_version})
