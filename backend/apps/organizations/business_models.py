"""Métiers, activités secondaires, habilitations douanières et agences.

Le métier dit ce qu'une société fait ; l'habilitation dit ce qu'elle a le droit de faire
devant la Douane. Le droit de préparer une déclaration ne vient jamais du seul métier choisi
(MET-01 à MET-06) : voir business_permissions.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel, OrganizationQuerySet, TimestampedModel


class BusinessProfile(models.TextChoices):
    TRANSIT = "transit", "Transitaire / commissionnaire"
    IMPORTER = "importer", "Importateur / exportateur"
    LOGISTICS = "logistics", "Logistique et transport"
    EXPERT = "expert", "Conseil et expertise douanière"


# Les quatre familles sont ouvertes à la création ; leurs espaces partagent le même moteur.
OPEN_PROFILES = frozenset(BusinessProfile.values)


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
    # Activités exercées en plus du métier principal (un groupe peut être importateur et logisticien).
    secondary_profiles = models.JSONField(default=list, blank=True)
    features = models.JSONField(default=list, blank=True)

    @property
    def profiles(self) -> list[str]:
        return [self.primary_profile, *[p for p in self.secondary_profiles if p != self.primary_profile]]


class CustomsHabilitation(OrganizationOwnedModel):
    """Habilitation douanière réelle d'une société, dans un pays, vérifiée par l'exploitant.

    Gabon / CEMAC (source : douanes.ga, page « Commissionnaires en douane », vérifiée le 2026-11-02) :
    agrément de commissionnaire (CD CEMAC art. 148 à 151, Règlement 11/10-UEAC-207-CM-21),
    autorisation provisoire de dédouaner (art. 150), déclaration par le propriétaire des
    marchandises pour son propre compte, expert en douane agréé (Acte 3/96-UDEAC-1496-CD-57).
    """

    class Kind(models.TextChoices):
        CUSTOMS_BROKER = "customs_broker", "Agrément de commissionnaire en douane"
        TEMPORARY_AUTHORIZATION = "temporary_authorization", "Autorisation provisoire de dédouaner"
        OWN_ACCOUNT = "own_account", "Déclaration pour compte propre"
        CUSTOMS_EXPERT = "customs_expert", "Expert en douane agréé"

    class Status(models.TextChoices):
        DECLARED = "declared", "Déclarée, à vérifier"
        VERIFIED = "verified", "Vérifiée"
        REVOKED = "revoked", "Retirée"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    country_code = models.CharField(max_length=2)
    # Numéro ou référence de l'acte, toujours en texte.
    reference = models.CharField(max_length=120)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DECLARED)
    note = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["country_code", "kind", "-created_at"]

    def in_force(self, day) -> bool:
        if self.status != self.Status.VERIFIED:
            return False
        if self.valid_from and day < self.valid_from:
            return False
        return not (self.valid_until and day > self.valid_until)


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
