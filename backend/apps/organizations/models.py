"""Sociétés de transit (locataires) et affiliations des utilisateurs."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import TimestampedModel


class Role(models.TextChoices):
    DECLARANT = "declarant", "Déclarant"
    VALIDATOR = "validator", "Validateur"
    ORG_ADMIN = "org_admin", "Administrateur de société"


def default_validation_policy():
    # Politique versionnée : H04, séparation préparateur/validateur à confirmer au pilote.
    return {"version": 1, "require_distinct_validator": True}


class Organization(TimestampedModel):
    name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, default="Africa/Libreville")
    default_locale = models.CharField(
        max_length=2, default="fr",
        choices=[("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")]
    )
    validation_policy = models.JSONField(default=default_validation_policy)
    active = models.BooleanField(default=True)
    # Les jeux de démonstration sont repérables pour ne jamais être confondus avec des données réelles.
    is_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "société"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(TimestampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    roles = ArrayField(models.CharField(max_length=32, choices=Role.choices), default=list, blank=True)
    active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "affiliation"
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="uniq_membership_org_user"),
        ]

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    def __str__(self):
        return f"{self.user} @ {self.organization}"
