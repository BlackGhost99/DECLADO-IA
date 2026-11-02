import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0004_organization_max_agencies"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationbusinessprofile",
            name="secondary_profiles",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="organizationbusinessprofile",
            name="primary_profile",
            field=models.CharField(
                choices=[
                    ("transit", "Transitaire / commissionnaire"),
                    ("importer", "Importateur / exportateur"),
                    ("logistics", "Logistique et transport"),
                    ("expert", "Conseil et expertise douanière"),
                ],
                default="transit",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="CustomsHabilitation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("customs_broker", "Agrément de commissionnaire en douane"),
                            ("temporary_authorization", "Autorisation provisoire de dédouaner"),
                            ("own_account", "Déclaration pour compte propre"),
                            ("customs_expert", "Expert en douane agréé"),
                        ],
                        max_length=30,
                    ),
                ),
                ("country_code", models.CharField(max_length=2)),
                ("reference", models.CharField(max_length=120)),
                ("valid_from", models.DateField(blank=True, null=True)),
                ("valid_until", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("declared", "Déclarée, à vérifier"), ("verified", "Vérifiée"), ("revoked", "Retirée")],
                        default="declared",
                        max_length=10,
                    ),
                ),
                ("note", models.CharField(blank=True, default="", max_length=500)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["country_code", "kind", "-created_at"]},
        ),
    ]
