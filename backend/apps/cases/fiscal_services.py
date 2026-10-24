"""Read only published fiscal rules scoped by territory, regime, tariff code and date."""
from django.db.models import Q

from apps.tariffs.fiscal_models import FiscalRule

from .fiscal_applicability import VerifiedFiscalRule, select_applicable_rules


def applicable_rules(*, territory, regime, tariff_code, on_date):
    candidates = FiscalRule.objects.filter(
        published=True,
        territory=territory,
        regime=regime,
        tariff_code=tariff_code,
        valid_from__lte=on_date,
    ).filter(
        Q(valid_to__isnull=True)
        | __import__("django").db.models.Q(valid_to__gt=on_date)
    )
    rules = [
        VerifiedFiscalRule(
            code=item.code,
            rate_percent=item.rate_percent,
            base=item.base,
            territory=item.territory,
            regime=item.regime,
            tariff_code=item.tariff_code,
            valid_from=item.valid_from,
            valid_to=item.valid_to,
            legal_reference=item.legal_reference,
            verification_id=str(item.pk),
            published=item.published,
        )
        for item in candidates
    ]
    return select_applicable_rules(
        rules=rules,
        territory=territory,
        regime=regime,
        tariff_code=tariff_code,
        on_date=on_date,
    )
