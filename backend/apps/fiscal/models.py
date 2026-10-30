"""Barème des taxes et modifications de taux (TAX-01 à TAX-05).

Le barème importé est commun à toute la plateforme : aucune société ne le possède ni ne le
modifie. Une modification de taux est un ajout daté et sourcé, jamais une réécriture :
le barème importé reste tel que lu, et un calcul se refait à l'identique pour une date donnée.
"""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class TaxCode(models.TextChoices):
    DDI = "DDI", "Droit de douane import"
    DA = "DA", "Droit d'accise"
    TVA = "TVA", "Taxe sur la valeur ajoutée"
    TCI = "TCI", "Taxe communautaire d'intégration"
    CCI = "CCI", "Contribution communautaire d'intégration"
    OAD = "OAD", "Prélèvement OHADA"
    CSS = "CSS", "Contribution spéciale de solidarité"
    CAF = "CAF", "Contribution pour l'Union africaine"
    RI = "RI", "Redevance informatique"
    DSO = "DSO", "Droit de sortie"


class TaxSchedule(UUIDModel):
    """Barème importé d'un classeur (feuille par code SH) ; un seul barème actif par territoire."""

    label = models.CharField(max_length=200)
    territory = models.CharField(max_length=10, default="GA")
    source = models.ForeignKey("tariffs.SourceDocument", on_delete=models.PROTECT, related_name="+")
    edition = models.ForeignKey(
        "tariffs.TariffEdition", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sheet = models.CharField(max_length=100)
    reference_sheet = models.CharField(max_length=100, blank=True)
    counts = models.JSONField(default=dict)
    is_active = models.BooleanField(default=False)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "barème des taxes"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["territory"], condition=models.Q(is_active=True), name="uniq_active_schedule_territory"
            )
        ]

    def __str__(self):
        return self.label


class ScheduleLine(UUIDModel):
    """Ligne du barème : code à 8 chiffres et sous-position nationale, textes, zéros conservés."""

    schedule = models.ForeignKey(TaxSchedule, on_delete=models.PROTECT, related_name="lines")
    hs_code = models.CharField(max_length=8)
    national_code = models.CharField(max_length=3)
    label = models.TextField(blank=True)
    unit = models.CharField(max_length=10, blank=True)
    row_number = models.PositiveIntegerField()
    # Valeurs de la feuille de référence (TEC), telles que lues : comparaison seulement.
    reference = models.JSONField(default=dict, blank=True)
    review = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["schedule", "row_number"]
        indexes = [models.Index(fields=["schedule", "hs_code"])]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "row_number"], name="uniq_schedule_line_row"),
        ]


class ScheduleRate(UUIDModel):
    """Taux lu dans une cellule. Vide = inconnu, jamais zéro (seule l'accise vide vaut « pas d'accise »)."""

    line = models.ForeignKey(ScheduleLine, on_delete=models.PROTECT, related_name="rates")
    tax = models.CharField(max_length=5, choices=TaxCode.choices)
    raw_value = models.CharField(max_length=40, blank=True)
    rate = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    cell = models.CharField(max_length=12)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["line", "tax"], name="uniq_schedule_rate_tax")]


class TaxAmendment(models.Model):
    """Modification d'un taux par l'admin ClairTransit : ajout seul, daté, sourcé, motivé.

    `hs_code` vide : la modification vaut pour tous les codes (taux unique ou redevance).
    """

    class SourceKind(models.TextChoices):
        FINANCE_LAW = "finance_law", "Loi de finances"
        CEMAC_ACT = "cemac_act", "Directive ou règlement CEMAC"
        CUSTOMS_CIRCULAR = "customs_circular", "Circulaire des Douanes"
        OPERATOR = "operator", "Décision de l'exploitant, sans texte officiel"

    territory = models.CharField(max_length=10, default="GA")
    sequence = models.PositiveIntegerField()
    tax = models.CharField(max_length=5, choices=TaxCode.choices)
    hs_code = models.CharField(max_length=8, blank=True)
    national_code = models.CharField(max_length=3, blank=True)
    rate = models.DecimalField(max_digits=9, decimal_places=4)
    previous_rate = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    effective_from = models.DateField()
    source_kind = models.CharField(max_length=20, choices=SourceKind.choices)
    source_reference = models.CharField(max_length=300, blank=True)
    reason = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "modification de taux"
        ordering = ["territory", "sequence"]
        constraints = [models.UniqueConstraint(fields=["territory", "sequence"], name="uniq_amendment_sequence")]

    def __str__(self):
        return f"{self.territory} #{self.sequence} {self.tax} {self.hs_code or 'tous codes'} = {self.rate}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Une modification de taux n'est jamais réécrite : en enregistrer une nouvelle.")
        super().save(*args, **kwargs)
