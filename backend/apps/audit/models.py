"""Journal d'audit append-only (AUD-01, AUD-02).

La base refuse aussi UPDATE et DELETE sur cette table (déclencheur posé par migration).
Le contenu sensible (texte de factures, descriptions) ne doit pas y être recopié.
"""

import uuid

from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    pass


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    event_type = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64)
    previous = models.JSONField(null=True, blank=True)
    current = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]
        indexes = [
            models.Index(fields=["organization", "-at"]),
            models.Index(fields=["organization", "event_type"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.event_type} {self.entity_type}:{self.entity_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Le journal d'audit est en ajout seul.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Le journal d'audit est en ajout seul.")
