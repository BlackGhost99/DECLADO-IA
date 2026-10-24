"""Profils métier et agences, sans modifier le modèle historique Organization."""
from django.db import models

from apps.core.models import TimestampedModel


class BusinessProfile(models.TextChoices):
    TRANSIT = "transit", "Commissionnaire / transit"
    IMPORTER = "importer", "Grand importateur"
    LOGISTICS = "logistics", "Logisticien intégré"
    EXPERT = "expert", "Expert douanier"


class OrganizationBusinessProfile(TimestampedModel):
    organization = models.OneToOneField(
        "organizations.Organization", related_name="business_profile",
        on_delete=models.PROTECT,
    )
    primary_profile = models.CharField(
        max_length=20, choices=BusinessProfile.choices, default=BusinessProfile.TRANSIT,
    )
    features = models.JSONField(default=list, blank=True)


class Agency(TimestampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", related_name="agencies", on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    country_code = models.CharField(max_length=2, default="GA")
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_agency_code_org"),
        ]
