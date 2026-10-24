"""Pièces déposées par une société : original immuable, empreinte, versions (DOC-02)."""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel

from .sniff import LABELS, READABILITY_LABELS, Readability


class Document(OrganizationOwnedModel):
    """Original conservé tel que reçu. Un remplacement crée un nouveau Document (supersedes)."""

    object_key = models.CharField(max_length=200, unique=True, editable=False)
    original_name = models.CharField(max_length=255)
    mime = models.CharField(max_length=120)  # type déterminé par le contenu
    declared_mime = models.CharField(max_length=120, blank=True)  # type annoncé par le client
    bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by"
    )
    readability = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in READABILITY_LABELS.items()],
        default=Readability.OK,
    )
    inspection_notes = models.JSONField(default=list, blank=True)
    # Determined by a future detector; never guessed from the user interface locale.
    detected_locale = models.CharField(max_length=2, blank=True, default="", choices=[("", "Unknown"), ("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")])
    language_detection = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "pièce"
        indexes = [models.Index(fields=["organization", "sha256"])]

    def __str__(self):
        return f"{self.original_name} v{self.version}"

    @property
    def type_label(self) -> str:
        return LABELS.get(self.mime, self.mime)

    @property
    def previewable(self) -> bool:
        return self.readability == Readability.OK
