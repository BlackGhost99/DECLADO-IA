import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tariffs", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FiscalRule",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("code", models.CharField(max_length=40)),
                ("tariff_code", models.CharField(max_length=20)),
                ("territory", models.CharField(max_length=2)),
                ("regime", models.CharField(max_length=60)),
                ("base", models.CharField(max_length=40, choices=[
                    ("customs_value", "Customs value"),
                    ("customs_value_plus_duties", "Customs value plus duties"),
                ])),
                ("rate_percent", models.DecimalField(max_digits=12, decimal_places=6)),
                ("valid_from", models.DateField()),
                ("valid_to", models.DateField(null=True, blank=True)),
                ("legal_reference", models.CharField(max_length=500)),
                ("source_url", models.URLField(blank=True)),
                ("verification_note", models.TextField()),
                ("verified_at", models.DateTimeField()),
                ("published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(null=True, blank=True)),
                ("verified_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="fiscalrule",
            constraint=models.CheckConstraint(
                condition=models.Q(rate_percent__gte=0, rate_percent__lte=100),
                name="fiscal_rule_rate_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="fiscalrule",
            constraint=models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True)
                | models.Q(valid_to__gt=models.F("valid_from")),
                name="fiscal_rule_date_interval_valid",
            ),
        ),
    ]
