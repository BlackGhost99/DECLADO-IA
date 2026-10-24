"""Many-to-many documentary associations within one case revision."""
from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class DocumentRelation(OrganizationOwnedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposée"
        CONFIRMED = "confirmed", "Confirmée"
        REJECTED = "rejected", "Rejetée"

    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="document_relations")
    source = models.ForeignKey("cases.CaseDocument", on_delete=models.PROTECT, related_name="outgoing_relations")
    target = models.ForeignKey("cases.CaseDocument", on_delete=models.PROTECT, related_name="incoming_relations")
    kind = models.CharField(max_length=30, choices=[
        ("same_shipment", "Même expédition"),
        ("supports_invoice", "Justifie une facture"),
        ("shared_insurance", "Assurance commune"),
        ("shared_transport", "Transport commun"),
        ("other", "Autre lien"),
    ])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROPOSED)
    provenance = models.CharField(
        max_length=20, choices=[("manual", "Manuel"), ("suggested", "Suggéré")], default="manual"
    )
    rationale = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="graph_distinct_documents"),
            models.UniqueConstraint(fields=["revision", "source", "target", "kind"], name="graph_unique_relation"),
        ]
