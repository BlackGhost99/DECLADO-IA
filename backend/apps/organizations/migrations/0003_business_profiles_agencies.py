import uuid

import django.db.models.deletion
from django.db import migrations, models


def seed_profiles(apps, schema_editor):
    # Les sociétés existantes gardent le profil transit (PR #7).
    Organization = apps.get_model("organizations", "Organization")
    Profile = apps.get_model("organizations", "OrganizationBusinessProfile")
    for organization in Organization.objects.all().iterator():
        Profile.objects.get_or_create(
            organization_id=organization.pk,
            defaults={"primary_profile": "transit", "features": []},
        )


class Migration(migrations.Migration):
    dependencies = [("organizations", "0002_organization_default_locale")]

    operations = [
        migrations.CreateModel(
            name="Agency",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(max_length=40)),
                ("country_code", models.CharField(default="GA", max_length=2)),
                ("active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="agencies",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="OrganizationBusinessProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                (
                    "primary_profile",
                    models.CharField(
                        choices=[
                            ("transit", "Commissionnaire / transit"),
                            ("importer", "Grand importateur"),
                            ("logistics", "Logisticien intégré"),
                            ("expert", "Expert douanier"),
                        ],
                        default="transit",
                        max_length=20,
                    ),
                ),
                ("features", models.JSONField(blank=True, default=list)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="business_profile",
                        to="organizations.organization",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="agency",
            constraint=models.UniqueConstraint(fields=("organization", "code"), name="uniq_agency_code_org"),
        ),
        migrations.AddField(
            model_name="organization",
            name="country_code",
            field=models.CharField(default="GA", max_length=2),
        ),
        migrations.AddField(
            model_name="organization",
            name="max_users",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="membership",
            name="agency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="organizations.agency",
            ),
        ),
        migrations.RunPython(seed_profiles, migrations.RunPython.noop),
    ]
