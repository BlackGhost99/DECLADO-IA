import uuid
import django.db.models.deletion
from django.db import migrations, models


def seed_profiles(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Profile = apps.get_model("organizations", "OrganizationBusinessProfile")
    for organization in Organization.objects.all().iterator():
        Profile.objects.get_or_create(
            organization_id=organization.pk,
            defaults={"primary_profile": "transit", "features": []},
        )


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Agency",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(max_length=40)),
                ("country_code", models.CharField(max_length=2, default="GA")),
                ("active", models.BooleanField(default=True)),
                ("organization", models.ForeignKey(to="organizations.organization", related_name="agencies", on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.CreateModel(
            name="OrganizationBusinessProfile",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("primary_profile", models.CharField(max_length=20, default="transit", choices=[("transit", "Commissionnaire / transit"), ("importer", "Grand importateur"), ("logistics", "Logisticien intégré"), ("expert", "Expert douanier")])),
                ("features", models.JSONField(default=list, blank=True)),
                ("organization", models.OneToOneField(to="organizations.organization", related_name="business_profile", on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(
            model_name="agency",
            constraint=models.UniqueConstraint(fields=("organization", "code"), name="uniq_agency_code_org"),
        ),
        migrations.RunPython(seed_profiles, migrations.RunPython.noop),
    ]
