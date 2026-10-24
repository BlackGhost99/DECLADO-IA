"""Profils métier et agences, sans modifier le modèle historique Organization.

Repris de la PR #7 (socle multi-métiers) pour la mise en route : le métier est choisi à la
création de la société et chaque affiliation peut être rattachée à une agence.
"""

from django.db import models

from apps.core.models import OrganizationQuerySet, TimestampedModel


class BusinessProfile(models.TextChoices):
    TRANSIT = "transit", "Commissionnaire / transit"
    IMPORTER = "importer", "Grand importateur"
    LOGISTICS = "logistics", "Logisticien intégré"
    EXPERT = "expert", "Expert douanier"


# Métiers ouverts à la création d'une société. Les autres restent annoncés « plus tard » (V1 : transit).
OPEN_PROFILES = frozenset({BusinessProfile.TRANSIT})


class OrganizationBusinessProfile(TimestampedModel):
    organization = models.OneToOneField(
        "organizations.Organization",
        related_name="business_profile",
        on_delete=models.PROTECT,
    )
    primary_profile = models.CharField(
        max_length=20,
        choices=BusinessProfile.choices,
        default=BusinessProfile.TRANSIT,
    )
    features = models.JSONField(default=list, blank=True)


class Agency(TimestampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="agencies",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    country_code = models.CharField(max_length=2, default="GA")
    active = models.BooleanField(default=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_agency_code_org"),
        ]

    def __str__(self):
        return self.name
