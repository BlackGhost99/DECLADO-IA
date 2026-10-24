"""Mise en route : demandes d'ouverture d'espace et invitations à activer un compte.

Aucun mot de passe n'est choisi pour autrui : l'invité le crée lui-même depuis son lien.
Les jetons ne sont jamais stockés en clair (empreinte SHA-256 seulement).
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import OrganizationOwnedModel, TimestampedModel
from apps.organizations.business_models import BusinessProfile
from apps.organizations.models import Role


class AccessRequest(TimestampedModel):
    """Demande d'espace envoyée par une entreprise ; rien n'est créé avant l'accord de l'exploitant."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        REFUSED = "refused", "Refusée"

    company_name = models.CharField(max_length=200)
    primary_profile = models.CharField(max_length=20, choices=BusinessProfile.choices)
    country_code = models.CharField(max_length=2)
    # Texte, jamais un entier : les identifiants officiels gardent leur forme d'origine.
    registration_number = models.CharField(max_length=80)
    contact_name = models.CharField(max_length=200)
    contact_role = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=40, blank=True)
    preferred_locale = models.CharField(max_length=2, default="fr")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_name} ({self.status})"


class Invitation(OrganizationOwnedModel):
    """Lien d'activation à usage unique, valable un temps limité, pour rejoindre une société."""

    email = models.EmailField()
    full_name = models.CharField(max_length=200, blank=True)
    roles = ArrayField(models.CharField(max_length=32, choices=Role.choices), default=list)
    agency = models.ForeignKey(
        "organizations.Agency", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "email"])]

    def __str__(self):
        return f"{self.email} → {self.organization_id}"
