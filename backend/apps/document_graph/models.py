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
    kind = models.CharField(
        max_length=30,
        choices=[
            ("same_shipment", "Même expédition"),
            ("supports_invoice", "Justifie une facture"),
            ("shared_insurance", "Assurance commune"),
            ("shared_transport", "Transport commun"),
            ("other", "Autre lien"),
        ],
    )
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


class Shipment(OrganizationOwnedModel):
    """Expédition proposée depuis une référence de transport ou créée par l'agent."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "À confirmer"
        CONFIRMED = "confirmed", "Confirmée"

    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="graph_shipments")
    reference = models.CharField(max_length=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROPOSED)
    method = models.CharField(max_length=40, default="exact-reference-v1")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["revision", "reference"], name="graph_unique_shipment")]


class ShipmentDocument(OrganizationOwnedModel):
    """Une pièce peut couvrir plusieurs expéditions, et réciproquement."""

    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="document_links")
    document = models.ForeignKey("cases.CaseDocument", on_delete=models.PROTECT, related_name="shipment_links")
    status = models.CharField(max_length=12, choices=DocumentRelation.Status.choices, default="proposed")
    evidence = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shipment", "document"], name="graph_unique_shipment_document")
        ]


class ShipmentInvoice(OrganizationOwnedModel):
    """Relation M:N indépendante des liens document-facture."""

    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="invoice_links")
    invoice = models.ForeignKey("cases.Invoice", on_delete=models.PROTECT, related_name="shipment_links")
    status = models.CharField(max_length=12, choices=DocumentRelation.Status.choices, default="proposed")
    evidence = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shipment", "invoice"], name="graph_unique_shipment_invoice")]


class DocumentInvoiceLink(OrganizationOwnedModel):
    """Association M:N explicite : assurance, colisage ou fret commun à plusieurs factures."""

    class Kind(models.TextChoices):
        INVOICE_REFERENCE = "invoice_reference", "Référence de facture"
        PACKING = "packing", "Colisage"
        INSURANCE = "insurance", "Assurance"
        FREIGHT = "freight", "Fret"
        TRANSPORT = "transport", "Transport"
        OTHER = "other", "Autre"

    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="graph_invoice_links")
    document = models.ForeignKey("cases.CaseDocument", on_delete=models.PROTECT, related_name="graph_invoice_links")
    invoice = models.ForeignKey("cases.Invoice", on_delete=models.PROTECT, related_name="graph_document_links")
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.INVOICE_REFERENCE)
    status = models.CharField(max_length=12, choices=DocumentRelation.Status.choices, default="proposed")
    evidence = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "document", "invoice", "kind"], name="graph_unique_document_invoice"
            )
        ]


class DocumentConflict(OrganizationOwnedModel):
    """Contradiction documentaire non destructrice, résolue par une décision attribuée."""

    class Status(models.TextChoices):
        OPEN = "open", "À examiner"
        RESOLVED = "resolved", "Résolue"

    revision = models.ForeignKey("cases.CaseRevision", on_delete=models.PROTECT, related_name="graph_conflicts")
    document = models.ForeignKey(
        "cases.CaseDocument", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    invoice = models.ForeignKey("cases.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=40)
    key = models.CharField(max_length=160)
    detail = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["revision", "kind", "key"], name="graph_unique_conflict")
        ]
