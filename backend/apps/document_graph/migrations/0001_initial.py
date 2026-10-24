import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("cases", "0001_initial"),
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="DocumentRelation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("kind", models.CharField(max_length=30, choices=[
                    ("same_shipment", "Même expédition"), ("supports_invoice", "Justifie une facture"),
                    ("shared_insurance", "Assurance commune"), ("shared_transport", "Transport commun"),
                    ("other", "Autre lien"),
                ])),
                ("status", models.CharField(max_length=12, default="proposed", choices=[
                    ("proposed", "Proposée"), ("confirmed", "Confirmée"), ("rejected", "Rejetée")])),
                ("provenance", models.CharField(max_length=20, default="manual", choices=[
                    ("manual", "Manuel"), ("suggested", "Suggéré")])),
                ("rationale", models.CharField(max_length=500, blank=True)),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("organization", models.ForeignKey(to="organizations.organization", on_delete=django.db.models.deletion.PROTECT, related_name="+")),
                ("revision", models.ForeignKey(to="cases.caserevision", on_delete=django.db.models.deletion.PROTECT, related_name="document_relations")),
                ("source", models.ForeignKey(to="cases.casedocument", on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_relations")),
                ("target", models.ForeignKey(to="cases.casedocument", on_delete=django.db.models.deletion.PROTECT, related_name="incoming_relations")),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="+")),
                ("reviewed_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="+")),
            ],
        ),
        migrations.AddConstraint(
            model_name="documentrelation",
            constraint=models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="graph_distinct_documents"),
        ),
        migrations.AddConstraint(
            model_name="documentrelation",
            constraint=models.UniqueConstraint(fields=["revision", "source", "target", "kind"], name="graph_unique_relation"),
        ),
    ]
