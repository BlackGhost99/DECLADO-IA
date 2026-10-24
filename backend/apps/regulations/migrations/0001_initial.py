# Migration initiale du référentiel réglementaire (Django 5.2).
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        ("cases", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=60, unique=True)),
                ("label_fr", models.CharField(max_length=160)),
                ("label_en", models.CharField(blank=True, max_length=160)),
                ("description", models.TextField(blank=True)),
                ("active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="RegulatorySource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(max_length=120, unique=True)),
                ("title", models.CharField(max_length=300)),
                ("scope", models.CharField(choices=[("CEMAC", "Communautaire CEMAC"), ("NATIONAL", "National")], max_length=12)),
                ("country_code", models.CharField(blank=True, max_length=2)),
                ("official_url", models.URLField(max_length=500)),
                ("adopted_on", models.DateField(blank=True, null=True)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("verified_on", models.DateField(blank=True, null=True)),
                ("verification_notes", models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("article", models.CharField(max_length=80)),
                ("operation", models.CharField(blank=True, max_length=24)),
                ("regime", models.CharField(blank=True, max_length=60)),
                ("transport_mode", models.CharField(blank=True, max_length=30)),
                ("conditions", models.JSONField(blank=True, default=dict)),
                ("stage", models.CharField(choices=[("collection", "Collecte"), ("calculation", "Calcul"), ("declaration", "Déclaration")], default="declaration", max_length=20)),
                ("valid_from", models.DateField(blank=True, null=True)),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("verified", models.BooleanField(default=False)),
                ("published", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("document_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requirements", to="regulations.documenttype")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requirements", to="regulations.regulatorysource")),
            ],
            options={
                "indexes": [models.Index(fields=["published", "verified", "valid_from"], name="regulations_publish_idx")],
                "constraints": [models.CheckConstraint(
                    condition=models.Q(valid_until__isnull=True) | models.Q(valid_from__isnull=True) | models.Q(valid_until__gt=models.F("valid_from")),
                    name="doc_req_valid_interval",
                )],
            },
        ),
        migrations.CreateModel(
            name="CompanyDocumentPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation", models.CharField(blank=True, max_length=24)),
                ("regime", models.CharField(blank=True, max_length=60)),
                ("transport_mode", models.CharField(blank=True, max_length=30)),
                ("active", models.BooleanField(default=True)),
                ("reason", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="regulations.documenttype")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_policies", to="organizations.organization")),
            ],
            options={"indexes": [models.Index(fields=["organization", "active"], name="regulations_org_active_idx")]},
        ),
        migrations.CreateModel(
            name="RequirementEvaluation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot", models.JSONField()),
                ("evaluated_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("revision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_evaluations", to="cases.caserevision")),
            ],
            options={"ordering": ["-evaluated_at"]},
        ),
    ]
