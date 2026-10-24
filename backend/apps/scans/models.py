"""Numérisation des pièces d'un dossier (NUM-01 à NUM-08).

Un lot reçoit les pages venues du scanner (PDF multipage, images) ou du téléphone. Chaque page
est lue, puis le lot est découpé en pièces proposées. Rien n'est rattaché au dossier avant que
l'agent ne valide le découpage ; les originaux déposés restent conservés tels quels.
"""

from django.conf import settings
from django.db import models

from apps.cases.models import CaseDocument
from apps.core.models import OrganizationOwnedModel


class ScanBatch(OrganizationOwnedModel):
    class Source(models.TextChoices):
        SCANNER = "scanner", "Scanner"
        CAMERA = "camera", "Téléphone ou webcam"

    class State(models.TextChoices):
        OPEN = "open", "En cours de numérisation"
        PROCESSING = "processing", "Lecture des pages"
        TO_SORT = "to_sort", "À trier"
        ATTACHED = "attached", "Rattaché au dossier"
        CANCELLED = "cancelled", "Abandonné"

    case = models.ForeignKey("cases.CustomsCase", on_delete=models.PROTECT, related_name="scan_batches")
    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="scan_batches")
    source = models.CharField(max_length=20, choices=Source.choices)
    label = models.CharField(max_length=200)
    state = models.CharField(max_length=20, choices=State.choices, default=State.OPEN)
    job = models.ForeignKey("core.BackgroundJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    attached_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    attached_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "lot numérisé"
        ordering = ["-created_at"]


class ScanSource(OrganizationOwnedModel):
    """Fichier déposé dans le lot (original conservé comme pièce de la société)."""

    batch = models.ForeignKey(ScanBatch, on_delete=models.PROTECT, related_name="sources")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    ordinal = models.PositiveIntegerField()
    page_count = models.PositiveIntegerField(null=True, blank=True)  # inconnu tant que le fichier n'est pas ouvert
    split_done = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["ordinal"]
        constraints = [models.UniqueConstraint(fields=["batch", "ordinal"], name="uniq_scan_source_ordinal")]


class ScanPiece(OrganizationOwnedModel):
    """Pièce proposée (ou formée par l'agent) ; devient une pièce du dossier au rattachement."""

    batch = models.ForeignKey(ScanBatch, on_delete=models.PROTECT, related_name="pieces")
    ordinal = models.PositiveIntegerField()
    usage = models.CharField(max_length=20, choices=CaseDocument.Usage.choices, default=CaseDocument.Usage.OTHER)
    # Pourquoi ce type est proposé (« FACTURE » lu en haut de la page 1) ou « choisi par l'agent ».
    reason = models.CharField(max_length=300, blank=True)
    usage_by_user = models.BooleanField(default=False)
    case_document = models.OneToOneField(
        CaseDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="scan_piece"
    )

    class Meta:
        ordering = ["ordinal"]


class ScanPage(OrganizationOwnedModel):
    class State(models.TextChoices):
        PENDING = "pending", "À lire"
        READ = "read", "Lue"
        FAILED = "failed", "Illisible"

    class Removal(models.TextChoices):
        NONE = "", "Conservée"
        BLANK = "blank", "Page blanche retirée"
        USER = "user", "Retirée par l'agent"
        REPLACED = "replaced", "Remplacée par une reprise"

    batch = models.ForeignKey(ScanBatch, on_delete=models.PROTECT, related_name="pages")
    source = models.ForeignKey(ScanSource, on_delete=models.PROTECT, related_name="pages")
    source_page = models.PositiveIntegerField()  # numéro de page dans le fichier d'origine (1…)
    # Position dans le lot ; une reprise prend la position de la page qu'elle remplace.
    position = models.DecimalField(max_digits=12, decimal_places=4)
    image_key = models.CharField(max_length=200, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    rotation = models.PositiveSmallIntegerField(default=0)  # 0, 90, 180, 270 (sens horaire)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    text_origin = models.CharField(max_length=20, blank=True)  # « pdf_text », « ocr » ou vide
    text = models.TextField(blank=True)
    title = models.CharField(max_length=120, blank=True)  # titre reconnu, tel que lu
    title_usage = models.CharField(max_length=20, blank=True)
    reference = models.CharField(max_length=80, blank=True)  # numéro de pièce lu près du titre
    page_marker = models.CharField(max_length=20, blank=True)  # « 1/3 » lu sur la page
    blank = models.BooleanField(default=False)
    hard_to_read = models.BooleanField(default=False)
    notes = models.JSONField(default=list, blank=True)
    removed = models.CharField(max_length=20, choices=Removal.choices, blank=True, default=Removal.NONE)
    replaced_by = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replaces")
    piece = models.ForeignKey(ScanPiece, null=True, blank=True, on_delete=models.PROTECT, related_name="pages")
    sorted = models.BooleanField(default=False)  # déjà passée par le découpage automatique

    class Meta:
        ordering = ["position"]
