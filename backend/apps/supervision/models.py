"""Journal de fonctionnement de la plateforme, lu par l'exploitant ClairTransit (SUP-01).

On y note ce qui n'a pas abouti et ne laisse pas de trace ailleurs : pièce refusée (antivirus,
format, taille), antivirus indisponible, action refusée, erreur serveur, essai de l'antivirus.
Une demande refusée est annulée en base (ATOMIC_REQUESTS) : ces notes sont écrites après la
réponse, hors de sa transaction. Aucun contenu de pièce, aucun nom de fichier, aucune valeur lue :
seulement des codes, des messages de l'application, des tailles, des types et des empreintes
tronquées. Append-only.
"""

import uuid

from django.conf import settings
from django.db import models


class OperationalEvent(models.Model):
    class Category(models.TextChoices):
        ANTIVIRUS = "antivirus", "Antivirus"
        DOCUMENT = "document", "Pièce refusée"
        REQUEST = "request", "Action refusée"
        SERVER = "server", "Erreur serveur"

    class Level(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Avertissement"
        ERROR = "error", "Erreur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    level = models.CharField(max_length=10, choices=Level.choices)
    code = models.CharField(max_length=60)
    message = models.CharField(max_length=300, blank=True)
    # Sans contrainte : une note ne doit jamais empêcher la suppression d'une société d'essai.
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    request_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "événement de fonctionnement"
        ordering = ["-at"]
        indexes = [models.Index(fields=["category", "-at"]), models.Index(fields=["organization", "-at"])]

    def __str__(self):
        return f"{self.category} {self.code} ({self.at:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Le journal de fonctionnement n'est jamais modifié.")
        super().save(*args, **kwargs)
