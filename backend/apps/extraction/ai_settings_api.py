"""Administration > IA en ligne : réglage de la société, consommation du mois, refus des clients, journal."""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.clients.models import Importer
from apps.core.exceptions import ApiError
from apps.onboarding.api import IsPlatformOperator
from apps.organizations.models import Organization, Role
from apps.organizations.permissions import require_roles

from . import ai, ai_completion
from .ai_settings_services import set_platform_quota
from .models import AICompletion, OrganizationAISettings

JOURNAL_SIZE = 30


def _journal(org) -> list[dict]:
    records = (
        AICompletion.objects.for_organization(org)
        .select_related("case_document__revision__case", "case_document__document", "created_by")
        .order_by("-created_at")[:JOURNAL_SIZE]
    )
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at,
            "case_id": str(r.case_document.revision.case_id),
            "case_reference": r.case_document.revision.case.reference,
            "file_name": r.case_document.document.original_name,
            "usage": r.case_document.usage,
            "detected_type": r.case_document.detected_type or None,
            "status": r.status,
            "status_label": r.get_status_display(),
            "trigger": r.trigger,
            "provider": r.provider or None,
            "model": r.model or None,
            "free_tier": r.free_tier,
            "requested": len(r.requested),
            "found": len(r.found),
            "rejected": len(r.rejected),
            "cost_estimate": str(r.cost_estimate) if r.cost_estimate is not None else None,
            "error_message": r.error_message or None,
            "by": r.created_by.full_name or r.created_by.email,
        }
        for r in records
    ]


def _usage(org, cap: int) -> dict:
    sent = AICompletion.objects.for_organization(org).filter(
        status=AICompletion.Status.SENT, created_at__gte=ai_completion.month_start()
    )
    costs = list(sent.values_list("cost_estimate", flat=True))
    known = all(c is not None for c in costs)
    return {
        "month_start": ai_completion.month_start(),
        "sent": len(costs),
        "cap": cap,
        # Un coût inconnu n'est jamais compté pour zéro : le total est alors inconnu.
        "cost_estimate": str(sum(costs, Decimal("0"))) if known else None,
    }


def payload(org) -> dict:
    config = ai_completion.settings_for(org)
    refusing = Importer.objects.for_organization(org).filter(ai_refused=True).select_related("ai_refused_by")
    return {
        "enabled": config.enabled,
        "mode": config.mode,
        "monthly_cap": config.monthly_cap,
        "row_version": 0 if config._state.adding else config.row_version,  # pas encore enregistré : 0
        "provider": ai.provider_info(),
        "usage": _usage(org, config.monthly_cap),
        "refusing_clients": [
            {
                "id": str(i.id),
                "name": i.name,
                "refused_at": i.ai_refused_at,
                "refused_by": (i.ai_refused_by.full_name or i.ai_refused_by.email) if i.ai_refused_by else None,
            }
            for i in refusing
        ],
        "journal": _journal(org),
    }


class AISettingsInput(serializers.Serializer):
    enabled = serializers.BooleanField()
    mode = serializers.ChoiceField(choices=OrganizationAISettings.Mode.choices)
    monthly_cap = serializers.IntegerField(min_value=0, max_value=100000, required=False)
    row_version = serializers.IntegerField(min_value=0)


class OrganizationAISettingsView(APIView):
    permission_classes = [require_roles(Role.ORG_ADMIN)]

    def get(self, request):
        return Response(payload(request.organization))

    def put(self, request):
        serializer = AISettingsInput(data=request.data)
        if not serializer.is_valid():
            raise ApiError("INVALID_REQUEST", "Requête invalide.", 400, serializer.errors)
        data = serializer.validated_data
        org = request.organization
        if data["enabled"] and not ai.is_enabled():
            raise ApiError(
                "AI_NOT_CONFIGURED", "Aucune clé de fournisseur d'IA sur ce serveur : l'exploitant doit l'ajouter.", 409
            )
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=org.pk)
            config = OrganizationAISettings.objects.for_organization(org).select_for_update().first()
            cap = config.monthly_cap if config else OrganizationAISettings().monthly_cap
            if "monthly_cap" in data and data["monthly_cap"] != cap:
                raise ApiError("AI_CAP_OPERATOR_ONLY", "Seul l'exploitant fixe le plafond de la société.", 403)
            current = config.row_version if config else 0
            if data["row_version"] != current:
                raise ApiError("ROW_VERSION_CONFLICT", "Réglage modifié entre-temps : recharger la page.", 409)
            before = None
            if config is not None:
                before = {"enabled": config.enabled, "mode": config.mode, "monthly_cap": config.monthly_cap}
            if config is None:
                config = OrganizationAISettings(organization=org)
            else:
                config.row_version += 1
            config.enabled, config.mode = data["enabled"], data["mode"]
            config.updated_by = request.user
            config.save()
            record_event(
                organization=org,
                actor=request.user,
                event_type="organization.ai_settings_updated",
                entity=config,
                previous=before,
                current={
                    "enabled": config.enabled,
                    "mode": config.mode,
                    "monthly_cap": config.monthly_cap,
                    "provider": ai.provider_info()["name"],
                },  # fmt: skip
            )
        return Response(payload(org))


def platform_summary(org):
    """Console exploitant : limites et totaux uniquement, aucun dossier ni client."""
    config = ai_completion.settings_for(org)
    return {
        "id": str(org.pk),
        "name": org.name,
        "monthly_cap": config.monthly_cap,
        "row_version": 0 if config._state.adding else config.row_version,
        "usage": _usage(org, config.monthly_cap),
    }


class PlatformAISettingsView(APIView):
    permission_classes = [IsPlatformOperator]

    def get(self, request):
        return Response(
            {
                "provider": ai.provider_info(),
                "organizations": [platform_summary(org) for org in Organization.objects.order_by("name", "id")],
            }
        )


class PlatformQuotaInput(serializers.Serializer):
    monthly_cap = serializers.IntegerField(min_value=0, max_value=100000)
    row_version = serializers.IntegerField(min_value=0)


class PlatformAIQuotaView(APIView):
    permission_classes = [IsPlatformOperator]

    def put(self, request, organization_id):
        serializer = PlatformQuotaInput(data=request.data)
        if not serializer.is_valid():
            raise ApiError("INVALID_REQUEST", "Requête invalide.", 400, serializer.errors)
        data = serializer.validated_data
        org = set_platform_quota(
            organization_id=organization_id,
            actor=request.user,
            monthly_cap=data["monthly_cap"],
            row_version=data["row_version"],
        )
        return Response(platform_summary(org))
