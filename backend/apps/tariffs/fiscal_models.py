"""Verified fiscal rules: distinct from imported tariff observations."""
from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel


class FiscalRule(TimestampedModel):
    code = models.CharField(max_length=40)
    tariff_code = models.CharField(max_length=20)
    territory = models.CharField(max_length=2)
    regime = models.CharField(max_length=60)
    base = models.CharField(max_length=40, choices=[
        ("customs_value", "Customs value"),
        ("customs_value_plus_duties", "Customs value plus duties"),
    ])
    rate_percent = models.DecimalField(max_digits=12, decimal_places=6)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    legal_reference = models.CharField(max_length=500)
    source_url = models.URLField(blank=True)
    verification_note = models.TextField()
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
    )
    verified_at = models.DateTimeField()
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate_percent__gte=0, rate_percent__lte=100),
                name="fiscal_rule_rate_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True)
                | models.Q(valid_to__gt=models.F("valid_from")),
                name="fiscal_rule_date_interval_valid",
            ),
        ]
