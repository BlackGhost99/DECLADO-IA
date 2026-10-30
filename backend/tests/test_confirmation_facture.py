"""Confirmation d'une valeur lue sur la facture (EXT-08, T72) et rattachement de l'importateur.

Facture BatiPro fictive : la raison sociale du fournisseur est lue en tête de page, donc « à vérifier ».
"""

import pytest

from apps.audit.models import AuditEvent
from apps.cases.models import Invoice
from apps.core import outbox
from tests.test_lecture_pieces import INVOICE, _private_storage, batipro, read_piece  # noqa: F401


@pytest.fixture
def invoice(batipro):  # noqa: F811
    case, links = batipro
    read_piece(case, links[INVOICE])
    return case, Invoice.objects.get(), links


def flagged(inv):
    return {f["field"] for f in inv.review_flags}


def test_t72_confirmed_value_is_no_longer_to_verify_and_survives_a_reread(invoice):
    case, inv, links = invoice
    assert "supplier_name" in flagged(inv)
    resp = case["s"].post(f"/api/v1/invoices/{inv.id}/fields/supplier_name/confirm", {"row_version": inv.row_version})
    assert resp.status_code == 200, resp.content
    assert resp.json()["field_origins"]["supplier_name"] == "confirmed"
    inv.refresh_from_db()
    assert "supplier_name" not in flagged(inv) and inv.supplier_name == "Iberica Industrial Components S.L."
    event = AuditEvent.objects.get(event_type="invoice.field_confirmed")
    assert event.current == {"field": "supplier_name", "origin": "confirmed"}  # le nom du champ, pas le texte lu
    # Une nouvelle lecture garde la valeur confirmée et ne la remet pas « à vérifier ».
    resp = case["s"].post(f"/api/v1/case-documents/{links[INVOICE]['id']}/extractions", {"retry": True})
    assert resp.status_code == 202, resp.content
    assert outbox.dispatch_pending() >= 1
    inv.refresh_from_db()
    assert inv.field_origins["supplier_name"] == "confirmed" and "supplier_name" not in flagged(inv)


def test_t72_confirm_refuses_an_empty_or_unknown_field_and_a_stale_version(invoice):
    case, inv, _ = invoice
    url = f"/api/v1/invoices/{inv.id}/fields"
    Invoice.objects.filter(pk=inv.pk).update(incoterm="")
    inv.refresh_from_db()
    assert case["s"].post(f"{url}/incoterm/confirm", {"row_version": inv.row_version}).status_code == 400
    assert case["s"].post(f"{url}/row_version/confirm", {"row_version": inv.row_version}).status_code == 400
    assert case["s"].post(f"{url}/supplier_name/confirm", {"row_version": inv.row_version - 1}).status_code == 409


def test_t72_correction_and_cross_tenant(invoice, session):
    case, inv, _ = invoice
    resp = case["s"].patch(
        f"/api/v1/invoices/{inv.id}", {"supplier_name": "Iberica S.L.", "row_version": inv.row_version}
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["field_origins"]["supplier_name"] == "manual"
    inv.refresh_from_db()
    assert "supplier_name" not in flagged(inv)
    other = session("declarant@b.test")
    resp = other.post(f"/api/v1/invoices/{inv.id}/fields/supplier_name/confirm", {"row_version": inv.row_version})
    assert resp.status_code == 404
    inv.refresh_from_db()
    assert inv.field_origins["supplier_name"] == "manual"


def test_t72_importer_is_linked_from_the_buyer_read(invoice, world):
    case, _, _ = invoice
    detail = case["s"].get(f"/api/v1/cases/{case['id']}").json()
    created = case["s"].post("/api/v1/importers", {"name": "BatiPro Gabon SARL"})
    assert created.status_code == 201, created.content
    resp = case["s"].patch(
        f"/api/v1/cases/{case['id']}", {"importer_id": created.json()["id"], "row_version": detail["row_version"]}
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["importer"]["name"] == "BatiPro Gabon SARL"
    # L'importateur d'une autre société n'est pas rattachable.
    resp = case["s"].patch(
        f"/api/v1/cases/{case['id']}",
        {"importer_id": str(world["importer_b"].id), "row_version": resp.json()["row_version"]},
    )
    assert resp.status_code == 404
