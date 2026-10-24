"""Référentiel documentaire et réglementaire global ; les sociétés ne peuvent qu'ajouter des exigences."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class DocumentType(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    label_fr = models.CharField(max_length=160)
    label_en = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.label_fr


class RegulatorySource(models.Model):
    class Scope(models.TextChoices):
        CEMAC = "CEMAC", "Communautaire CEMAC"
        NATIONAL = "NATIONAL", "National"

    reference = models.CharField(max_length=120, unique=True)
    title = models.CharField(max_length=300)
    scope = models.CharField(max_length=12, choices=Scope.choices)
    country_code = models.CharField(max_length=2, blank=True)
    official_url = models.URLField(max_length=500)
    adopted_on = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    def __str__(self):
        return self.reference

    def clean(self):
        if self.scope == self.Scope.NATIONAL and not self.country_code:
            raise ValidationError({"country_code": "Pays requis pour une source nationale."})
        if self.scope == self.Scope.CEMAC and self.country_code:
            raise ValidationError({"country_code": "Une source CEMAC ne cible pas un seul pays."})


class DocumentRequirement(models.Model):
    class Stage(models.TextChoices):
        COLLECTION = "collection", "Collecte"
        CALCULATION = "calculation", "Calcul"
        DECLARATION = "declaration", "Déclaration"

    source = models.ForeignKey(RegulatorySource, on_delete=models.PROTECT, related_name="requirements")
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="requirements")
    article = models.CharField(max_length=80)
    operation = models.CharField(max_length=24, blank=True)
    regime = models.CharField(max_length=60, blank=True)
    transport_mode = models.CharField(max_length=30, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.DECLARATION)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["published", "verified", "valid_from"], name="regulations_publish_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(valid_until__isnull=True) | Q(valid_from__isnull=True) | Q(valid_until__gt=models.F("valid_from"))
                ),
                name="doc_req_valid_interval",
            )
        ]

    def __str__(self):
        return f"{self.document_type_id} — {self.source_id}"

    def clean(self):
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValidationError({"valid_until": "La fin doit suivre le début de validité."})
        if self.published and (
            not self.verified or not self.valid_from or not self.source_id or not self.source.verified_on
        ):
            raise ValidationError("Publication interdite sans vérification, date et source.")
        if not isinstance(self.conditions, dict):
            raise ValidationError({"conditions": "Objet JSON requis."})
        if set(self.conditions) - {"requires_previous_regime", "requires_privileged_regime"}:
            raise ValidationError({"conditions": "Condition non prise en charge ; laisser non publiée."})
        if any(not isinstance(v, bool) for v in self.conditions.values()):
            raise ValidationError({"conditions": "Les conditions connues doivent être booléennes."})


class CompanyDocumentPolicy(models.Model):
    """Exigences ajoutées par une société ; aucune fonction de désactivation de la loi."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="document_policies"
    )
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    operation = models.CharField(max_length=24, blank=True)
    regime = models.CharField(max_length=60, blank=True)
    transport_mode = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "active"], name="regulations_org_active_idx")]

    def __str__(self):
        return f"{self.organization_id}: {self.document_type_id}"


class RequirementEvaluation(models.Model):
    """Snapshot du calcul des exigences lié à une révision de dossier."""

    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="document_evaluations")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    snapshot = models.JSONField()
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-evaluated_at"]

    def __str__(self):
        return f"{self.revision_id} — {self.evaluated_at}"
