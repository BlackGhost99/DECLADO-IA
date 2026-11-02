"""Réglages de préparation de la société (T86) : régime et bureau d'entrée par défaut, cours de change.

Données fictives. Les valeurs ne sont proposées que dans un champ vide, « à confirmer » ; un cours
est daté et sourcé, en ajout seul, et celui retenu est en vigueur à la date prévue du dossier.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.cases.models import CompanyExchangeRate
from apps.extraction import synthetic
from tests.test_extraction import extracted, make_edition
from tests.test_preparation_auto import detail, new_case


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def usd_invoice():
    return synthetic.simple_invoice_pdf(header=synthetic._header_block(currency="USD"))


def test_t86_only_the_admin_sets_defaults_and_validators_add_dated_sourced_rates(world, session):
    admin, declarant, validator = session("admin@a.test"), session("declarant@a.test"), session("validateur@a.test")
    url = "/api/v1/organization/preparation-settings"
    assert declarant.get(url).json()["regime"] == ""
    assert declarant.put(url, {"regime": "IM4"}).status_code == 403
    resp = admin.put(url, {"regime": "IM4 (fictif)", "entry_office": "Owendo port (fictif)"})
    assert resp.status_code == 200, resp.content
    assert declarant.get(url).json()["entry_office"] == "Owendo port (fictif)"
    assert session("admin@b.test").get(url).json()["regime"] == ""  # autre société : ses propres réglages

    rates = "/api/v1/organization/exchange-rates"
    body = {"currency": "usd", "rate": "605.5", "valid_from": "2026-10-01", "source": "BEAC (fictif)"}
    assert declarant.post(rates, body).status_code == 403
    assert validator.post(rates, body | {"source": " "}).status_code == 400
    assert validator.post(rates, body | {"currency": "EUR"}).status_code == 400  # parité fixe
    assert validator.post(rates, body | {"rate": "0"}).status_code == 400
    resp = validator.post(rates, body)
    assert resp.status_code == 201, resp.content
    assert resp.json()["currency"] == "USD" and resp.json()["rate"] == "605.5"
    assert [r["currency"] for r in declarant.get(rates).json()["results"]] == ["USD"]
    assert session("declarant@b.test").get(rates).json()["results"] == []
    with pytest.raises(ValueError):
        CompanyExchangeRate.objects.first().save()
    assert AuditEvent.objects.filter(event_type="organization.exchange_rate_added").count() == 1
    assert AuditEvent.objects.filter(event_type="organization.preparation_settings_updated").count() == 1


def test_t86_reading_proposes_company_defaults_and_the_rate_in_force(world, session):
    make_edition()
    admin, validator, s = session("admin@a.test"), session("validateur@a.test"), session("declarant@a.test")
    admin.put("/api/v1/organization/preparation-settings", {"regime": "IM4 (fictif)", "entry_office": "Owendo"})
    today = timezone.localdate()
    for valid_from, rate in ((today - timedelta(days=30), "600"), (today, "605.5"), (today + timedelta(days=5), "700")):
        resp = validator.post("/api/v1/organization/exchange-rates",
                              {"currency": "USD", "rate": rate, "valid_from": valid_from.isoformat(),
                               "source": "BEAC (fictif)"})  # fmt: skip
        assert resp.status_code == 201
    case = new_case(s)
    _link, run = extracted(case, "facture.pdf", usd_invoice())
    assert run["status"] == "succeeded"
    rev = detail(case)
    assert rev["regime"] == "IM4 (fictif)" and rev["entry_office"] == "Owendo"
    usd = rev["exchange_rates"]["USD"]
    assert usd["rate"] == "605.5" and usd["source"].startswith(f"Cours de la société au {today:%d/%m/%Y}")
    assert {"regime", "entry_office", "exchange_rates"} <= set(rev["prefilled"])
    calc = s.get(f"/api/v1/cases/{case['id']}/calculation").json()
    assert calc["missing_rates"] == []
    # Enregistré par l'agent, le taux n'est plus une proposition.
    resp = s.patch(f"/api/v1/revisions/{case['revision']}",
                   {"exchange_rates": {"USD": usd}, "row_version": rev["row_version"]})  # fmt: skip
    assert resp.status_code == 200 and "exchange_rates" not in resp.json()["prefilled"]


def test_t86_a_filled_field_or_a_rate_already_entered_is_never_overwritten(world, session):
    make_edition()
    admin, validator, s = session("admin@a.test"), session("validateur@a.test"), session("declarant@a.test")
    admin.put("/api/v1/organization/preparation-settings", {"regime": "IM4 (fictif)"})
    validator.post("/api/v1/organization/exchange-rates",
                   {"currency": "USD", "rate": "605.5", "valid_from": "2026-01-01", "source": "BEAC"})  # fmt: skip
    case = new_case(s)
    resp = s.patch(f"/api/v1/revisions/{case['revision']}",
                   {"regime": "IM7", "exchange_rates": {"USD": {"rate": "610", "source": "Banque (fictif)"}},
                    "row_version": 1})  # fmt: skip
    assert resp.status_code == 200, resp.content
    extracted(case, "facture.pdf", usd_invoice())
    rev = detail(case)
    assert rev["regime"] == "IM7" and rev["exchange_rates"]["USD"]["rate"] == "610"
    assert "regime" not in rev["prefilled"] and "exchange_rates" not in rev["prefilled"]


def test_t86_no_rate_in_force_at_the_planned_date_proposes_nothing(world, session):
    make_edition()
    validator, s = session("validateur@a.test"), session("declarant@a.test")
    later = timezone.localdate() + timedelta(days=10)
    validator.post("/api/v1/organization/exchange-rates",
                   {"currency": "USD", "rate": "605.5", "valid_from": later.isoformat(), "source": "BEAC"})  # fmt: skip
    case = new_case(s)
    extracted(case, "facture.pdf", usd_invoice())
    assert detail(case)["exchange_rates"] == {}  # le cours futur n'est pas appliqué avant sa date d'effet
