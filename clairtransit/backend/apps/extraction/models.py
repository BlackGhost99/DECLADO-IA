"""Exécutions d'extraction, observations localisées, corrections et divergences (EXT-01 à EXT-08).

Source brute, extraction, correction et décision sont des objets distincts : une exécution ne
modifie jamais une exécution précédente ; une correction humaine est un ajout attribué ; une
contradiction entre une relecture et une correction devient une divergence à examiner.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class ExtractionRun(OrganizationOwnedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "En attente"
        RUNNING = "running", "En cours"
        SUCCEEDED = "succeeded", "Terminée"
        FAILED = "failed", "Échec (relance possible)"

    case_document = models.ForeignKey("cases.CaseDocument", on_delete=models.PROTECT, related_name="extraction_runs")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    job = models.OneToOneField("core.BackgroundJob", on_delete=models.PROTECT, related_name="extraction_run")
    parser = models.CharField(max_length=40)
    parser_version = models.CharField(max_length=20)
    schema_version = models.CharField(max_length=10)
    # Aucun fournisseur d'IA en V1 : champs nuls, renseignés seulement par un adaptateur réellement raccordé.
    provider = models.CharField(max_length=60, null=True, blank=True)  # noqa: DJ001 - absent ≠ vide
    model = models.CharField(max_length=60, null=True, blank=True)  # noqa: DJ001
    options = models.JSONField(default=dict)
    options_hash = models.CharField(max_length=64)
    attempt = models.PositiveIntegerField()
    previous_run = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    charges = models.JSONField(default=list, blank=True)  # frais, remises, taxes, sous-totaux, totaux lus
    invoice = models.ForeignKey("cases.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    merge_report = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "extraction"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["case_document", "attempt"], name="uniq_extraction_attempt"),
        ]

    def __str__(self):
        return f"{self.parser} #{self.attempt} ({self.status})"


class SourceSpan(OrganizationOwnedModel):
    """Localisation vérifiable : page physique (à partir de 1) et cadre normalisé 0–1 depuis le coin
    supérieur gauche de la page rendue, ou feuille et plage A1 pour Excel (aucune page inventée)."""

    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    page_index = models.PositiveIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    page_size = models.JSONField(null=True, blank=True)
    rotation = models.SmallIntegerField(default=0)
    sheet = models.CharField(max_length=100, blank=True)
    cell_range = models.CharField(max_length=40, blank=True)
    excerpt = models.CharField(max_length=200, blank=True)

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "page": self.page_index,
            "bbox": self.bbox,
            "page_size": self.page_size,
            "rotation": self.rotation,
            "sheet": self.sheet or None,
            "cell_range": self.cell_range or None,
            "excerpt": self.excerpt,
        }


class FieldObservation(OrganizationOwnedModel):
    """Valeur lue par une exécution, avec son libellé, son statut et sa preuve. Jamais modifiée."""

    class Origin(models.TextChoices):
        READ = "read", "Lu"
        OCR = "ocr", "Lu par OCR"
        INFERRED = "inferred", "Déduit"

    run = models.ForeignKey(ExtractionRun, on_delete=models.PROTECT, related_name="observations")
    entity_key = models.CharField(max_length=40)  # « invoice », « item-3 », « charge-2 »
    field_name = models.CharField(max_length=40)
    label = models.CharField(max_length=120, blank=True)
    raw_value = models.TextField(null=True, blank=True)  # noqa: DJ001 - absent ≠ vide
    parsed_value = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20)
    origin_type = models.CharField(max_length=20, choices=Origin.choices)
    confidence = models.FloatField(null=True, blank=True)
    notes = models.JSONField(default=list, blank=True)
    source_span = models.ForeignKey(SourceSpan, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    invoice = models.ForeignKey("cases.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    invoice_line = models.ForeignKey(
        "cases.InvoiceLine", null=True, blank=True, on_delete=models.PROTECT, related_name="field_observations"
    )

    class Meta:
        ordering = ["run", "entity_key", "field_name"]
        indexes = [models.Index(fields=["run", "entity_key"])]


class FieldCorrection(OrganizationOwnedModel):
    """Correction humaine d'une valeur extraite : ajout seul, séparé de l'extraction (EXT-07)."""

    invoice = models.ForeignKey("cases.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    invoice_line = models.ForeignKey(
        "cases.InvoiceLine", null=True, blank=True, on_delete=models.PROTECT, related_name="corrections"
    )
    field_name = models.CharField(max_length=40)
    previous = models.JSONField(null=True, blank=True)
    current = models.JSONField(null=True, blank=True)
    observation = models.ForeignKey(
        FieldObservation, null=True, blank=True, on_delete=models.PROTECT, related_name="corrections"
    )
    reason = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Une correction n'est jamais modifiée : en enregistrer une nouvelle.")
        super().save(*args, **kwargs)


class Divergence(OrganizationOwnedModel):
    """Une relecture contredit une valeur corrigée ou saisie : rien n'est écrasé, l'utilisateur tranche."""

    class State(models.TextChoices):
        OPEN = "open", "À examiner"
        KEPT = "kept", "Correction conservée"
        ACCEPTED = "accepted", "Nouvelle lecture retenue"

    class Kind(models.TextChoices):
        VALUE = "value", "Valeur différente"
        LINE_NOT_REREAD = "line_not_reread", "Ligne absente de la nouvelle lecture"

    run = models.ForeignKey(ExtractionRun, on_delete=models.PROTECT, related_name="divergences")
    invoice = models.ForeignKey("cases.Invoice", on_delete=models.PROTECT, related_name="divergences")
    invoice_line = models.ForeignKey(
        "cases.InvoiceLine", null=True, blank=True, on_delete=models.PROTECT, related_name="divergences"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.VALUE)
    field_name = models.CharField(max_length=40, blank=True)
    current_value = models.JSONField(null=True, blank=True)
    extracted_value = models.JSONField(null=True, blank=True)
    observation = models.ForeignKey(FieldObservation, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=State.choices, default=State.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at"]
