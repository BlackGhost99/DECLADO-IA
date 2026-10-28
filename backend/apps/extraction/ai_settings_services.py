"""Quotas IA attribués par l'exploitant, sans modifier le consentement des sociétés."""

from django.db import transaction

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.models import Organization

from .models import OrganizationAISettings


def set_platform_quota(*, organization_id, actor, monthly_cap, row_version):
    with transaction.atomic():
        org = Organization.objects.select_for_update().filter(pk=organization_id).first()
        if org is None:
            raise ApiError("NOT_FOUND", "Société introuvable.", 404)
        config = OrganizationAISettings.objects.for_organization(org).select_for_update().first()
        current = config.row_version if config else 0
        if row_version != current:
            raise ApiError("ROW_VERSION_CONFLICT", "Réglage modifié entre-temps : recharger la page.", 409)
        before = config.monthly_cap if config else OrganizationAISettings().monthly_cap
        if config is None:
            config = OrganizationAISettings(organization=org)
        else:
            config.row_version += 1
        config.monthly_cap = monthly_cap
        config.updated_by = actor
        config.save()
        record_event(
            organization=org,
            actor=actor,
            event_type="platform.ai_quota_updated",
            entity=config,
            previous={"monthly_cap": before},
            current={"monthly_cap": config.monthly_cap},
            scope="platform",
        )
    return org
