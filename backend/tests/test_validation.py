# ruff: noqa: F811  (fixtures importées de test_fiscal)
"""Circuit de validation interne (WF-01 à WF-03, T73 à T75), sur des données fictives.

Soumettre seulement sans point bloquant ; retourner pour correction avec un motif ; valider sur le
calcul soumis, figé ensuite. Un validateur peut valider ce qu'il a lui-même soumis (choix du 30/10/2026).
"""

from decimal import Decimal

import pytest

from apps.audit.models import AuditEvent
from apps.cases.models import RevisionDecision
from apps.fiscal.models import TaxAmendment
from tests.test_fiscal import _private_storage, confirm, edition, schedule  # noqa: F401


def ready_case(session, edition, email="validateur@a.test"):
    s = session(email)
    resp = s.post("/api/v1/cases", {"title": "Validation", "target_edition_id": str(edition.id)})
    assert resp.status_code == 201, resp.content
    body = resp.json()
    case = {"s": s, "id": body["id"], "revision": body["revision"]["id"]}
    return case, body


def complete(case, world, edition):
    s = case["s"]
    detail = s.get(f"/api/v1/cases/{case['id']}").json()
    data = {"importer_id": str(world["importer_a"].id), "row_version": detail["row_version"]}
    assert s.patch(f"/api/v1/cases/{case['id']}", data).status_code == 200
    rev = s.get(f"/api/v1/cases/{case['id']}").json()["revision"]
    resp = s.patch(f"/api/v1/revisions/{case['revision']}",
                   {"planned_declaration_date": "2026-11-02", "regime": "Mise à la consommation (fictif)",
                    "row_version": rev["row_version"]})  # fmt: skip
    assert resp.status_code == 200, resp.content
    inv = s.post(f"/api/v1/revisions/{case['revision']}/invoices",
                 {"supplier_name": "Fournisseur fictif", "invoice_number": "F-1", "invoice_date": "2026-10-01",
                  "currency": "XAF", "incoterm": "CIF", "declared_total": "549070"}).json()  # fmt: skip
    line = s.post(f"/api/v1/invoices/{inv['id']}/lines",
                  {"description_raw": "Selles fictives", "quantity": "1", "unit": "pcs", "unit_price": "549070",
                   "amount": "549070", "origin_country": "FR", "customs_code": "4201.00.00"})  # fmt: skip
    assert line.status_code == 201, line.content
    goods = s.post(f"/api/v1/revisions/{case['revision']}/goods-lines", {"invoice_line_ids": [line.json()["id"]]})
    confirm(case, goods.json(), edition)
    return s.get(f"/api/v1/cases/{case['id']}").json()


def act(case, action, version, **data):
    return case["s"].post(f"/api/v1/cases/{case['id']}/workflow/{action}", {"row_version": version, **data})


def test_t73_submission_is_refused_while_blocking_points_remain(world, schedule, edition, session):
    case, body = ready_case(session, edition)
    resp = act(case, "submit", body["revision"]["row_version"])
    assert resp.status_code == 409 and resp.json()["code"] == "SUBMISSION_BLOCKED"
    assert {b["field"] for b in resp.json()["details"]["blocking"]} >= {"importer", "invoices"}


def test_t74_submit_return_with_reason_then_validate_freezes_the_calculation(world, schedule, edition, session):
    case, _ = ready_case(session, edition)
    detail = complete(case, world, edition)
    assert detail["revision"]["completeness"]["blocking"] == []
    resp = act(case, "submit", detail["revision"]["row_version"])
    assert resp.status_code == 200, resp.content
    rev = resp.json()["revision"]
    assert rev["state"] == "to_validate" and not rev["is_editable"]
    # Plus de modification une fois soumis.
    inv = rev["invoices"][0]
    assert (
        case["s"]
        .patch(f"/api/v1/invoices/{inv['id']}", {"supplier_name": "X", "row_version": inv["row_version"]})
        .status_code
        == 409
    )

    assert act(case, "return", rev["row_version"], reason=" ").status_code == 400
    resp = act(case, "return", rev["row_version"], reason="Origine à justifier (essai fictif).")
    assert resp.status_code == 200, resp.content
    rev = resp.json()["revision"]
    assert rev["state"] == "to_correct" and rev["is_editable"]
    assert rev["decisions"][-1]["kind"] == "returned" and "Origine" in rev["decisions"][-1]["reason"]

    rev = act(case, "submit", rev["row_version"]).json()["revision"]
    resp = act(case, "validate", rev["row_version"])  # le validateur valide ce qu'il a soumis
    assert resp.status_code == 200, resp.content
    rev = resp.json()["revision"]
    assert rev["state"] == "validated" and [d["kind"] for d in rev["decisions"]] == [
        "submitted", "returned", "submitted", "validated"]  # fmt: skip
    assert AuditEvent.objects.filter(event_type="revision.validated").count() == 1
    frozen = case["s"].get(f"/api/v1/cases/{case['id']}/calculation").json()
    assert frozen["frozen"] is True and frozen["articles"][0]["taxes"][0]["amount"] == "54907"
    # Un taux modifié ensuite ne change pas le calcul validé.
    TaxAmendment.objects.create(tax="DDI", hs_code="42010000", rate=Decimal("20"), effective_from="2026-01-01",
                                source_kind="operator", reason="Essai fictif", sequence=1,
                                created_by=world["users"]["a_admin"])  # fmt: skip
    again = case["s"].get(f"/api/v1/cases/{case['id']}/calculation").json()
    assert again["articles"][0]["taxes"][0]["amount"] == "54907"
    with pytest.raises(ValueError):
        RevisionDecision.objects.last().save()


def test_t75_a_declarant_submits_but_cannot_validate_and_a_changed_rate_blocks_validation(
    world,
    schedule,
    edition,
    session,
):
    case, _ = ready_case(session, edition, email="declarant@a.test")
    detail = complete(case, world, edition)
    rev = act(case, "submit", detail["revision"]["row_version"]).json()["revision"]
    assert act(case, "validate", rev["row_version"]).status_code == 403
    assert act(case, "return", rev["row_version"], reason="non").status_code == 403
    validator = {**case, "s": session("validateur@a.test")}
    TaxAmendment.objects.create(tax="DDI", hs_code="42010000", rate=Decimal("20"), effective_from="2026-01-01",
                                source_kind="operator", reason="Essai fictif", sequence=1,
                                created_by=world["users"]["a_admin"])  # fmt: skip
    resp = act(validator, "validate", rev["row_version"])
    assert resp.status_code == 409 and resp.json()["code"] == "STALE_SUBMISSION"
    assert session("declarant@b.test").post(f"/api/v1/cases/{case['id']}/workflow/validate",
                                            {"row_version": rev["row_version"]}).status_code == 404  # fmt: skip
