"""Référentiel tarifaire versionné (lot 1).

Principes : la source brute est conservée telle quelle (RawTariffRecord) ; les nœuds,
notes et observations de taux en sont dérivés et gardent leur preuve ; les anomalies
restent visibles ; une édition publiée est immuable. Aucun taux historique n'est une
règle fiscale : ce sont des observations (lot 4 pour les profils fiscaux validés).
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class SourceKind(models.TextChoices):
    PDF = "pdf", "PDF original"
    XLSX = "xlsx", "Classeur Excel original"
    PDF_TEXT_EXTRACT = "pdf_text_extract", "Texte extrait d'un PDF (copie dérivée)"
    CSV_EXPORT = "csv_export", "Export CSV d'un classeur (copie dérivée)"


class SourceDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    original_name = models.CharField(max_length=300)
    kind = models.CharField(max_length=32, choices=SourceKind.choices)
    is_derived_copy = models.BooleanField(default=False)
    sha256 = models.CharField(max_length=64, unique=True)
    bytes = models.PositiveBigIntegerField()
    storage_path = models.CharField(max_length=500)
    # Provenance déclarée (non vérifiée) et vérifiée sont distinguées.
    publisher_claimed = models.CharField(max_length=300, blank=True)
    edition_label_claimed = models.CharField(max_length=200, blank=True)
    provenance_note = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ImportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Terminé"
        COMPLETED_WITH_ISSUES = "completed_with_issues", "Terminé avec anomalies"
        FAILED = "failed", "Échec"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="runs")
    importer_name = models.CharField(max_length=100)
    importer_version = models.CharField(max_length=20)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict)
    coverage = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.importer_name} {self.importer_version} ({self.started_at:%Y-%m-%d})"


class PublicationState(models.TextChoices):
    DRAFT = "draft", "Brouillon (revue)"
    CONSULTATION = "consultation", "Publiée pour consultation historique"
    OPERATIONAL = "operational", "Publiée pour usage opérationnel"
    WITHDRAWN = "withdrawn", "Retirée"


class TariffEdition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=200)
    hs_version = models.CharField(max_length=20, blank=True)
    territory_scope = models.CharField(max_length=50, default="CEMAC")
    # Intervalle [effective_from, effective_to) ; vide = inconnu, jamais « toujours applicable ».
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    applicability_verified = models.BooleanField(default=False)
    publication_state = models.CharField(
        max_length=20, choices=PublicationState.choices, default=PublicationState.DRAFT
    )
    import_run = models.OneToOneField(ImportRun, on_delete=models.PROTECT, related_name="edition")
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label

    @property
    def is_mutable(self) -> bool:
        return self.publication_state == PublicationState.DRAFT


class RawTariffRecord(models.Model):
    """Zone brute de la source : ligne CSV ou page de texte. Jamais modifiée ni dédupliquée."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ImportRun, on_delete=models.PROTECT, related_name="records")
    ordinal = models.PositiveIntegerField()
    # Localisation : page physique (indexée à 1) et numéro imprimé, ou feuille/plage A1.
    page_index = models.PositiveIntegerField(null=True, blank=True)
    printed_page = models.CharField(max_length=20, blank=True)
    sheet = models.CharField(max_length=100, blank=True)
    cell_range = models.CharField(max_length=50, blank=True)
    raw_cells = models.JSONField(default=list, blank=True)
    raw_text = models.TextField(blank=True)
    formula = models.TextField(blank=True)
    cached_value = models.TextField(blank=True)

    class Meta:
        ordering = ["run", "ordinal"]
        constraints = [models.UniqueConstraint(fields=["run", "ordinal"], name="uniq_record_run_ordinal")]

    def __str__(self):
        return f"{self.run_id}#{self.ordinal}"

    @property
    def location_label(self) -> str:
        if self.cell_range:
            return f"{self.sheet or 'feuille'} {self.cell_range}"
        if self.page_index:
            printed = f" (imprimée {self.printed_page})" if self.printed_page else ""
            return f"page {self.page_index}{printed}"
        return f"enregistrement {self.ordinal}"


class NodeKind(models.TextChoices):
    SECTION = "section", "Section"
    CHAPTER = "chapter", "Chapitre"
    HEADING = "heading", "Position"
    SUBHEADING = "subheading", "Sous-position"
    TARIFF_LINE = "tariff_line", "Ligne tarifaire"


class ValidationState(models.TextChoices):
    EXTRACTED = "extracted", "Extrait"
    DERIVED = "derived", "Déduit de la hiérarchie"
    REVIEW_REQUIRED = "review_required", "À vérifier"
    VALIDATED = "validated", "Validé"


class TariffNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(TariffEdition, on_delete=models.PROTECT, related_name="nodes")
    # Texte (zéros initiaux conservés) ; NULL pour les intertitres sans code, hors contrainte d'unicité.
    code = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001
    code_display = models.CharField(max_length=30, blank=True)
    kind = models.CharField(max_length=20, choices=NodeKind.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    display_order = models.PositiveIntegerField(default=0)
    label_raw = models.TextField(blank=True)
    label_clean = models.TextField(blank=True)
    label_damaged = models.BooleanField(default=False)
    full_path_label = models.TextField(blank=True)
    search_text = models.TextField(blank=True)
    declarable = models.BooleanField(default=False)
    validation_state = models.CharField(max_length=20, choices=ValidationState.choices)
    source_record = models.ForeignKey(
        RawTariffRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="nodes"
    )

    class Meta:
        ordering = ["edition", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "code"], condition=models.Q(code__isnull=False), name="uniq_node_code_in_edition"
            )
        ]
        indexes = [
            models.Index(fields=["edition", "code"]),
            GinIndex(fields=["search_text"], opclasses=["gin_trgm_ops"], name="tariffnode_search_trgm"),
        ]

    def __str__(self):
        return f"{self.code_display or self.code or '—'} {self.label_clean[:60]}"


class RateObservation(models.Model):
    """Valeur historique observée dans une source. Ni règle fiscale, ni taux applicable."""

    class Quality(models.TextChoices):
        KNOWN = "known", "Valeur lue"
        UNKNOWN = "unknown", "Absente (inconnue, ≠ 0)"
        UNPARSEABLE = "unparseable", "Illisible comme nombre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(TariffNode, on_delete=models.PROTECT, related_name="rate_observations")
    source_record = models.ForeignKey(RawTariffRecord, on_delete=models.PROTECT, related_name="+")
    column = models.CharField(max_length=30)  # intitulé de colonne tel qu'annoncé par la source
    column_index = models.PositiveSmallIntegerField(default=0)
    raw_value = models.CharField(max_length=100, blank=True)
    value = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    quality = models.CharField(max_length=20, choices=Quality.choices)

    class Meta:
        ordering = ["node", "column_index"]

    def __str__(self):
        return f"{self.column}={self.raw_value!r}"


class LegalNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(TariffEdition, on_delete=models.PROTECT, related_name="notes")
    scope_type = models.CharField(max_length=20)  # section / chapter
    scope_ref = models.CharField(max_length=20)  # « I », « 01 »…
    heading = models.CharField(max_length=300, blank=True)
    text_raw = models.TextField()
    source_record = models.ForeignKey(RawTariffRecord, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["edition", "scope_type", "scope_ref"]

    def __str__(self):
        return f"Note {self.scope_type} {self.scope_ref}"


class CodeOccurrence(models.Model):
    """Code vu dans une source sans nœud propre (doublon, continuation) : preuve conservée."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(TariffNode, on_delete=models.PROTECT, related_name="occurrences")
    source_record = models.ForeignKey(RawTariffRecord, on_delete=models.PROTECT, related_name="+")
    raw_code = models.CharField(max_length=40)
    line_no = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.raw_code


class ImportIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Informative"
        REVIEW = "review", "À vérifier"
        BLOCKING = "blocking", "Bloquante"

    class State(models.TextChoices):
        OPEN = "open", "Ouverte"
        RESOLVED = "resolved", "Résolue"

    class Resolution(models.TextChoices):
        ACCEPTED = "accepted", "Source acceptée telle quelle"
        CORRECTED = "corrected", "Corrigée (correction séparée du brut)"
        DISMISSED = "dismissed", "Écartée (sans objet)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ImportRun, on_delete=models.PROTECT, related_name="issues")
    record = models.ForeignKey(RawTariffRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    node = models.ForeignKey(TariffNode, null=True, blank=True, on_delete=models.PROTECT, related_name="issues")
    category = models.CharField(max_length=50)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    message = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.OPEN)
    resolution = models.CharField(max_length=20, choices=Resolution.choices, blank=True)
    resolution_reason = models.TextField(blank=True)
    resolution_evidence = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "created_at"]
        indexes = [models.Index(fields=["run", "category", "state"])]

    def __str__(self):
        return f"{self.category}: {self.message[:60]}"


class NodeCorrection(models.Model):
    """REF-05 : ancienne valeur, nouvelle valeur, justification, preuve. Ajout seul."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(TariffNode, on_delete=models.PROTECT, related_name="corrections")
    issue = models.ForeignKey(ImportIssue, null=True, blank=True, on_delete=models.PROTECT, related_name="corrections")
    field = models.CharField(max_length=50)
    previous = models.TextField(blank=True)
    current = models.TextField(blank=True)
    reason = models.TextField()
    evidence = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["node", "at"]

    def __str__(self):
        return f"{self.field}: {self.previous!r} → {self.current!r}"
