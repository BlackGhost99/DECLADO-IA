"""Partage d'un dossier entre deux sociétés (COL-01 à COL-07).

Le dossier reste la propriété de sa société (`organization`) ; la société partenaire n'y accède
que par un partage accepté, en lecture d'un instantané choisi, jamais par les écrans de travail.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel, TimestampedModel


class PartnerCode(TimestampedModel):
    """Code que la société communique à ses partenaires pour recevoir un dossier (pas d'annuaire)."""

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.PROTECT, related_name="partner_code"
    )
    code = models.CharField(max_length=20, unique=True)


class CaseShare(OrganizationOwnedModel):
    """`organization` = propriétaire du dossier ; `partner` = société invitée."""

    class Level(models.TextChoices):
        READ = "read", "Lecture"
        COMMENT = "comment", "Lecture et remarques"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Accepté"
        REFUSED = "refused", "Refusé"
        REVOKED = "revoked", "Retiré"

    case = models.ForeignKey("cases.CustomsCase", on_delete=models.PROTECT, related_name="shares")
    partner = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.READ)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    message = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Un seul partage vivant par dossier et par partenaire.
            models.UniqueConstraint(
                fields=["case", "partner"],
                condition=models.Q(status__in=["pending", "accepted"]),
                name="uniq_live_case_share",
            )
        ]

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.ACCEPTED


class CaseShareNote(TimestampedModel):
    """Remarque échangée sur un partage ; jamais modifiée ni supprimée (append-only)."""

    share = models.ForeignKey(CaseShare, on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    author_organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    text = models.TextField(max_length=2000)

    class Meta:
        ordering = ["created_at"]
