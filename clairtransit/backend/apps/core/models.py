"""Modèles abstraits partagés : horodatage, identifiant UUID, verrou optimiste, rattachement société."""

import uuid

from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class OrganizationQuerySet(models.QuerySet):
    def for_organization(self, organization):
        """Seul point d'entrée des lectures métier : borne la requête à une société."""
        if organization is None:
            return self.none()
        return self.filter(organization=organization)


class TimestampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    row_version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class OrganizationOwnedModel(TimestampedModel):
    """Objet propre à une société. Tout accès passe par `objects.for_organization(org)`."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        abstract = True


class OutboxEvent(UUIDModel):
    """Événement à traiter enregistré dans la même transaction que la donnée métier.

    Le worker peut recevoir plusieurs fois un même événement : le traitement est
    idempotent par identifiant (dispatched_at renseigné une seule fois).
    """

    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    # Prise en charge en cours (bail) ou nouvelle tentative différée après un échec.
    available_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["dispatched_at", "created_at"])]

    def __str__(self):
        return f"{self.topic} ({self.id})"


class BackgroundJob(OrganizationOwnedModel):
    """Travail long suivi par l'utilisateur (extraction, OCR, puis calculs et exports).

    L'état du travail est indépendant de l'état du dossier : un travail terminé ne valide rien.
    """

    class State(models.TextChoices):
        QUEUED = "queued", "En attente"
        RUNNING = "running", "En cours"
        SUCCEEDED = "succeeded", "Terminé"
        FAILED = "failed", "Échec (relance possible)"

    kind = models.CharField(max_length=40)
    state = models.CharField(max_length=20, choices=State.choices, default=State.QUEUED)
    phase = models.CharField(max_length=60, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    input_hash = models.CharField(max_length=64)
    scope = models.CharField(max_length=80, blank=True)
    result_ref = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "kind", "input_hash"])]

    def __str__(self):
        return f"{self.kind} {self.state} ({self.id})"
