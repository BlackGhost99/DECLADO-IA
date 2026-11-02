# ruff: noqa: F811  (fixtures importées)
"""Fin de vie d'un dossier (WF-05, WF-06, T97 à T99), sur des données fictives.

Après validation interne, l'agent indique le dépôt dans SYDONIA (n° et date saisis, jamais vérifiés) ;
le dossier s'archive en lecture seule et seul un administrateur l'en sort.
"""

from datetime import date, timedelta

from apps.audit.models import AuditEvent
from apps.cases.models import CustomsCase
from tests.test_fiscal import _private_storage, confirm, edition, schedule  # noqa: F401
from tests.test_validation import act, complete, ready_case


def validated_case(world, edition, session):
    case, _ = ready_case(session, edition)
    rev = complete(case, world, edition)["revision"]
    rev = act(case, "submit", rev["row_version"]).json()["revision"]
    rev = act(case, "validate", rev["row_version"]).json()["revision"]
    assert rev["state"] == "validated"
    return case, rev


def test_t97_lodging_is_recorded_after_internal_validation_only(world, schedule, edition, session):
    draft, body = ready_case(session, edition)
    resp = act(draft, "lodge", body["revision"]["row_version"], number="L 1234", lodged_on="2026-11-02")
    assert resp.status_code == 409  # pas encore validé

    case, rev = validated_case(world, edition, session)
    v = rev["row_version"]
    assert act(case, "lodge", v, number=" ", lodged_on="2026-11-02").json()["details"]["field"] == "number"
    future = (date.today() + timedelta(days=1)).isoformat()
    assert act(case, "lodge", v, number="L 1234", lodged_on=future).status_code == 400
    resp = act(case, "lodge", v, number="L  1234 ", lodged_on="2026-11-02")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    rev = body["revision"]
    assert (rev["customs_declaration_number"], rev["lodged_on"], rev["state"]) == ("L 1234", "2026-11-02", "validated")
    assert rev["decisions"][-1]["kind"] == "lodged"
    assert rev["decisions"][-1]["details"] == {"declaration_number": "L 1234", "lodged_on": "2026-11-02"}
    assert body["customs_declaration_number"] == "L 1234"
    assert (
        act(case, "lodge", rev["row_version"], number="L 9", lodged_on="2026-11-02").json()["code"] == "ALREADY_LODGED"
    )
    # Le calcul figé à la validation reste celui qui fait foi.
    assert case["s"].get(f"/api/v1/cases/{case['id']}/calculation").json()["frozen"] is True
    assert AuditEvent.objects.filter(event_type="revision.lodged").count() == 1


def test_t98_archive_is_read_only_and_keeps_the_frozen_calculation(world, schedule, edition, session):
    case, rev = validated_case(world, edition, session)
    declarant = {**case, "s": session("declarant@a.test")}
    assert act(declarant, "archive", rev["row_version"]).status_code == 403
    resp = act(case, "archive", rev["row_version"])  # validé : motif facultatif
    assert resp.status_code == 200, resp.content
    rev = resp.json()["revision"]
    assert rev["state"] == "archived" and not rev["is_editable"] and resp.json()["archived_at"]
    assert case["s"].get(f"/api/v1/cases/{case['id']}/calculation").json()["frozen"] is True
    inv = rev["invoices"][0]
    patch = case["s"].patch(f"/api/v1/invoices/{inv['id']}", {"supplier_name": "X", "row_version": inv["row_version"]})
    assert patch.status_code == 409
    assert case["s"].post(f"/api/v1/cases/{case['id']}/revisions", {"reason": "x"}).status_code == 409
    assert session("declarant@b.test").post(f"/api/v1/cases/{case['id']}/workflow/archive",
                                            {"row_version": rev["row_version"]}).status_code == 404  # fmt: skip


def test_t99_draft_archive_needs_a_reason_and_only_an_admin_restores(world, schedule, edition, session):
    case, body = ready_case(session, edition)
    v = body["revision"]["row_version"]
    assert act(case, "archive", v).status_code == 400
    rev = act(case, "archive", v, reason="Client a renoncé (fictif).").json()["revision"]
    assert rev["state"] == "archived"
    assert act(case, "restore", rev["row_version"], reason="Reprise").status_code == 403  # validateur
    admin = {**case, "s": session("admin@a.test")}
    assert act(admin, "restore", rev["row_version"]).status_code == 400
    resp = act(admin, "restore", rev["row_version"], reason="Le client relance l'opération (fictif).")
    assert resp.status_code == 200, resp.content
    rev = resp.json()["revision"]
    assert rev["state"] == "draft" and rev["is_editable"]
    assert CustomsCase.objects.get(pk=case["id"]).archived_at is None
    assert [d["kind"] for d in rev["decisions"]] == ["archived", "restored"]
