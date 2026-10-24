"""Expéditions, associations plusieurs-à-plusieurs et contradictions documentaires."""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


BASE = [
    ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
    ("created_at", models.DateTimeField(auto_now_add=True)),
    ("updated_at", models.DateTimeField(auto_now=True)),
    ("row_version", models.PositiveIntegerField(default=1)),
]


def owner():
    return models.ForeignKey("organizations.Organization", on_delete=django.db.models.deletion.PROTECT, related_name="+")


def author():
    return models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="+")


def reviewer():
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="+"
    )


def fk(to, related):
    return models.ForeignKey(to, on_delete=django.db.models.deletion.PROTECT, related_name=related)


LINK_STATUS = [
    ("proposed", "Proposée"), ("confirmed", "Confirmée"), ("rejected", "Rejetée")
]


class Migration(migrations.Migration):
    dependencies = [
        ("document_graph", "0001_initial"),
        ("cases", "0004_extraction_links"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Shipment",
            fields=BASE + [
                ("reference", models.CharField(max_length=100)),
                ("status", models.CharField(
                    max_length=12, default="proposed",
                    choices=[("proposed", "À confirmer"), ("confirmed", "Confirmée")]
                )),
                ("method", models.CharField(max_length=40, default="exact-reference-v1")),
                ("organization", owner()),
                ("revision", fk("cases.CaseRevision", "graph_shipments")),
                ("created_by", author()),
                ("confirmed_by", reviewer()),
            ],
        ),
        migrations.CreateModel(
            name="ShipmentDocument",
            fields=BASE + [
                ("status", models.CharField(max_length=12, choices=LINK_STATUS, default="proposed")),
                ("evidence", models.JSONField(default=list, blank=True)),
                ("organization", owner()),
                ("shipment", fk("document_graph.Shipment", "document_links")),
                ("document", fk("cases.CaseDocument", "shipment_links")),
                ("created_by", author()),
                ("reviewed_by", reviewer()),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="ShipmentInvoice",
            fields=BASE + [
                ("status", models.CharField(max_length=12, choices=LINK_STATUS, default="proposed")),
                ("evidence", models.JSONField(default=list, blank=True)),
                ("organization", owner()),
                ("shipment", fk("document_graph.Shipment", "invoice_links")),
                ("invoice", fk("cases.Invoice", "shipment_links")),
                ("created_by", author()),
                ("reviewed_by", reviewer()),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentInvoiceLink",
            fields=BASE + [
                ("kind", models.CharField(
                    max_length=24, default="invoice_reference",
                    choices=[
                        ("invoice_reference", "Référence de facture"),
                        ("packing", "Colisage"), ("insurance", "Assurance"),
                        ("freight", "Fret"), ("transport", "Transport"), ("other", "Autre"),
                    ],
                )),
                ("status", models.CharField(max_length=12, choices=LINK_STATUS, default="proposed")),
                ("evidence", models.JSONField(default=list, blank=True)),
                ("organization", owner()),
                ("revision", fk("cases.CaseRevision", "graph_invoice_links")),
                ("document", fk("cases.CaseDocument", "graph_invoice_links")),
                ("invoice", fk("cases.Invoice", "graph_document_links")),
                ("created_by", author()),
                ("reviewed_by", reviewer()),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentConflict",
            fields=BASE + [
                ("kind", models.CharField(max_length=40)),
                ("key", models.CharField(max_length=160)),
                ("detail", models.JSONField(default=dict)),
                ("status", models.CharField(
                    max_length=12, default="open",
                    choices=[("open", "À examiner"), ("resolved", "Résolue")]
                )),
                ("resolution", models.CharField(max_length=500, blank=True)),
                ("organization", owner()),
                ("revision", fk("cases.CaseRevision", "graph_conflicts")),
                ("document", models.ForeignKey(
                    "cases.CaseDocument", null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT, related_name="+"
                )),
                ("invoice", models.ForeignKey(
                    "cases.Invoice", null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT, related_name="+"
                )),
                ("created_by", author()),
                ("resolved_by", reviewer()),
                ("resolved_at", models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="shipment",
            constraint=models.UniqueConstraint(fields=["revision", "reference"], name="graph_unique_shipment"),
        ),
        migrations.AddConstraint(
            model_name="shipmentdocument",
            constraint=models.UniqueConstraint(fields=["shipment", "document"], name="graph_unique_shipment_document"),
        ),
        migrations.AddConstraint(
            model_name="shipmentinvoice",
            constraint=models.UniqueConstraint(fields=["shipment", "invoice"], name="graph_unique_shipment_invoice"),
        ),
        migrations.AddConstraint(
            model_name="documentinvoicelink",
            constraint=models.UniqueConstraint(
                fields=["revision", "document", "invoice", "kind"], name="graph_unique_document_invoice"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentconflict",
            constraint=models.UniqueConstraint(fields=["revision", "kind", "key"], name="graph_unique_conflict"),
        ),
    ]
