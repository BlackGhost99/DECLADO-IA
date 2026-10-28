"""Importateurs clients d'une société de transit (CLI-01, version socle).

Premier objet métier borné à la société : il sert de support aux tests d'isolation
du lot 0. Le module complet (recherche des anciens dossiers, CLI-02) arrive au lot 2.
"""

import re
import unicodedata

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


class Importer(OrganizationOwnedModel):
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False, db_index=True)
    # Identifiants déclarés (NIF, RCCM…) conservés en texte tels que saisis.
    identifiers = models.JSONField(default=dict, blank=True)
    contacts = models.JSONField(default=list, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Le client refuse que ses pièces soient lues par une IA en ligne : prioritaire sur le réglage de la société.
    ai_refused = models.BooleanField(default=False)
    ai_refused_at = models.DateTimeField(null=True, blank=True)
    ai_refused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "importateur"
        ordering = ["name"]
        indexes = [models.Index(fields=["organization", "normalized_name"])]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
