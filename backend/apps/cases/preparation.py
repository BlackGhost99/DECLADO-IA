"""Réglages de préparation de la société : régime et bureau d'entrée par défaut, cours de change.

Ces valeurs sont proposées dans un dossier seulement quand le champ y est vide, marquées « à
confirmer » (CaseRevision.prefilled) jusqu'à ce qu'un agent les enregistre. Un cours de change
est saisi par la société avec sa date et sa source, jamais téléchargé ni deviné ; il est en ajout
seul, et le cours retenu est celui en vigueur à la date de déclaration prévue du dossier.
"""

import re
from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.fiscal.calculation import FIXED_RATES

from .models import CompanyExchangeRate, PreparationSettings


def settings_for(org) -> PreparationSettings | None:
    return PreparationSettings.objects.for_organization(org).first()


def settings_payload(org) -> dict:
    s = settings_for(org)
    return {
        "regime": s.regime if s else "",
        "entry_office": s.entry_office if s else "",
        "updated_at": s.updated_at if s else None,
        "updated_by": (s.updated_by.full_name or s.updated_by.email) if s and s.updated_by else None,
    }


@transaction.atomic
def update_settings(*, org, actor, data: dict) -> PreparationSettings:
    s = PreparationSettings.objects.for_organization(org).select_for_update().first()
    if s is None:
        s = PreparationSettings(organization=org)
    before = {"regime": s.regime, "entry_office": s.entry_office}
    for field in ("regime", "entry_office"):
        if field in data:
            setattr(s, field, (data[field] or "").strip())
    s.updated_by = actor
    s.save()
    after = {"regime": s.regime, "entry_office": s.entry_office}
    if after != before:
        record_event(
            organization=org,
            actor=actor,
            event_type="organization.preparation_settings_updated",
            entity=s,
            previous=before,
            current=after,
        )
    return s


def rate_payload(r: CompanyExchangeRate) -> dict:
    return {
        "id": str(r.id),
        "currency": r.currency,
        "rate": format(r.rate.normalize(), "f"),
        "valid_from": r.valid_from,
        "source": r.source,
        "created_at": r.created_at,
        "created_by": r.created_by.full_name or r.created_by.email,
    }


def rates(org):
    return CompanyExchangeRate.objects.for_organization(org).select_related("created_by")


@transaction.atomic
def add_rate(*, org, actor, currency: str, rate: Decimal, valid_from: date, source: str) -> CompanyExchangeRate:
    currency = (currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ApiError("VALIDATION_ERROR", "Devise : code ISO à trois lettres (USD, CNY…).", 400)
    if currency in FIXED_RATES:
        raise ApiError("VALIDATION_ERROR", f"{currency} : parité fixe, aucun cours à saisir.", 400)
    if rate is None or rate <= 0:
        raise ApiError("VALIDATION_ERROR", "Le cours doit être supérieur à zéro.", 400)
    source = (source or "").strip()
    if not source:
        raise ApiError("SOURCE_REQUIRED", "Indiquer la source du cours (BEAC, banque, Douane…).", 400)
    item = CompanyExchangeRate.objects.create(
        organization=org, currency=currency, rate=rate, valid_from=valid_from, source=source, created_by=actor
    )
    record_event(
        organization=org,
        actor=actor,
        event_type="organization.exchange_rate_added",
        entity=item,
        current={
            "currency": currency,
            "rate": format(rate.normalize(), "f"),
            "valid_from": valid_from.isoformat(),
            "source": source,
        },  # fmt: skip
    )
    return item


def rate_on(org, currency: str, on: date) -> CompanyExchangeRate | None:
    """Cours de la société en vigueur à cette date : le plus récent dont la date d'effet est passée."""
    return (
        CompanyExchangeRate.objects.for_organization(org)
        .filter(currency=(currency or "").upper(), valid_from__lte=on)
        .order_by("-valid_from", "-created_at")
        .first()
    )


def proposed_rate(org, currency: str, on: date) -> dict | None:
    """Taux à proposer dans un dossier, avec sa source lisible ; None sans cours de la société."""
    item = rate_on(org, currency, on)
    if item is None:
        return None
    return {
        "rate": format(item.rate.normalize(), "f"),
        "source": f"Cours de la société au {item.valid_from:%d/%m/%Y} ({item.source})"[:200],
    }
