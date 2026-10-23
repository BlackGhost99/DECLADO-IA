"""Lot 2, dossiers et contrôle d'un code présent : T01, T03, T04, T07, T11, T12, T13, T33."""

from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRevision, ClassificationDecision, CodeObservation, CustomsCase
from apps.organizations.models import Membership, Role
from apps.tariffs.importers.csv_export import import_csv
from apps.tariffs.importers.pdf_text import import_pdf_text
from apps.tariffs.services import publish_edition
from tests.conftest import PASSWORD

FIXTURES = Path(settings.BASE_DIR).parent / "fixtures" / "synthetic"


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def editions(db):
    manager = User.objects.create_user(email="ref@test.test", password=PASSWORD, is_reference_manager=True)
    csv = import_csv(FIXTURES / "referentiel-f.csv", edition_label="Jeu F CSV", title="referentiel-f.csv")
    text = import_pdf_text(FIXTURES / "referentiel-f.txt", edition_label="Jeu F texte", title="referentiel-f.txt")
    for edition in (csv, text):
        publish_edition(edition=edition, actor=manager, mode="consultation")
    return {"csv": csv, "text": text}


def create_case(s, **data):
    resp = s.post("/api/v1/cases", data)
    assert resp.status_code == 201, resp.content
    return resp.json()


def add_invoice(s, revision_id, **data):
    body = {
        "supplier_name": "Fournisseur fictif",
        "invoice_number": "F-1",
        "invoice_date": "2026-09-01",
        "currency": "EUR",
    }
    resp = s.post(f"/api/v1/revisions/{revision_id}/invoices", body | data)
    assert resp.status_code == 201, resp.content
    return resp.json()


def add_line(s, invoice_id, **data):
    body = {
        "description_raw": "Chevaux reproducteurs fictifs",
        "quantity": "2",
        "unit": "NMB",
        "unit_price": "1500.00",
        "amount": "3000.00",
        "origin_country": "fr",
    }
    resp = s.post(f"/api/v1/invoices/{invoice_id}/lines", body | data)
    assert resp.status_code == 201, resp.content
    return resp.json()


def add_goods(s, revision_id, line_ids, **data):
    resp = s.post(f"/api/v1/revisions/{revision_id}/goods-lines", {"invoice_line_ids": line_ids} | data)
    assert resp.status_code == 201, resp.content
    return resp.json()


def check(s, goods_id, edition):
    resp = s.post(f"/api/v1/goods-lines/{goods_id}/code-checks", {"edition_id": str(edition.id)})
    assert resp.status_code == 201, resp.content
    return resp.json()


@pytest.fixture
def prepared(world, editions, session):
    """Dossier de A : une facture, une ligne avec code douanier et référence fournisseur, une marchandise."""
    s = session("declarant@a.test")
    case = create_case(
        s,
        importer_id=str(world["importer_a"].id),
        planned_declaration_date="2026-10-15",
        regime="C100",
        target_edition_id=str(editions["csv"].id),
    )
    rev = case["revision"]["id"]
    inv = add_invoice(s, rev, declared_total="3000")
    line = add_line(s, inv["id"], customs_code="0101.10.00", customs_code_label="HS Code", source_reference="12345678")
    goods = add_goods(s, rev, [line["id"]])
    return {"s": s, "case": case, "rev": rev, "invoice": inv, "line": line, "goods": goods}


# --- Dossiers, références, filtres (T03, DOS-01) ---------------------------------------


def test_reference_unique_per_organization_and_mode(world, session):
    a, b = session("declarant@a.test"), session("declarant@b.test")
    first, second = create_case(a), create_case(a)
    other = create_case(b)
    assert first["reference"].endswith("-0001") and second["reference"].endswith("-0002")
    assert other["reference"].endswith("-0001")
    assert first["revision"]["revision_no"] == 1 and first["state"] == "draft"
    # Aucune édition opérationnelle n'existe : le dossier n'est jamais présenté comme opérationnel.
    assert first["mode"] == CaseRevision.Mode.HISTORICAL


def test_case_filters(world, session):
    s = session("validateur@a.test")
    mine = create_case(s, importer_id=str(world["importer_a"].id), title="Chevaux")
    create_case(s, title="Autre")
    declarant = world["users"]["a_declarant"]
    s.post(f"/api/v1/cases/{mine['id']}/assign", {"assignee_id": str(declarant.id), "row_version": 1})

    def refs(**params):
        return [c["reference"] for c in s.get("/api/v1/cases", **params).json()["results"]]

    assert refs(importer=str(world["importer_a"].id)) == [mine["reference"]]
    assert refs(assigned_to=str(declarant.id)) == [mine["reference"]]
    assert len(refs(assigned_to="none")) == 1
    assert refs(q="cheva") == [mine["reference"]]
    assert len(refs(state="draft")) == 2 and refs(state="validated") == []
    assert len(refs(created_from="2000-01-01")) == 2 and refs(created_to="2000-01-01") == []
    assert s.get("/api/v1/cases", importer="pas-un-uuid").status_code == 400


def test_importer_of_other_organization_cannot_be_linked(world, session):
    s = session("declarant@a.test")
    resp = s.post("/api/v1/cases", {"importer_id": str(world["importer_b"].id)})
    assert resp.status_code == 404
    resp = s.post("/api/v1/cases", {"organization_id": str(world["org_b"].id)})
    assert CustomsCase.objects.get(pk=resp.json()["id"]).organization == world["org_a"]


def test_roles_server_side(world, session):
    assert session("admin@a.test").post("/api/v1/cases", {}).status_code == 403
    assert session("declarant@a.test").post("/api/v1/cases", {}).status_code == 201


def test_assignment_rules(world, session):
    declarant = session("declarant@a.test")
    case = create_case(declarant)
    url = f"/api/v1/cases/{case['id']}/assign"
    me = world["users"]["a_declarant"]
    validator = world["users"]["a_validator"]
    assert declarant.post(url, {"assignee_id": str(validator.id), "row_version": 1}).status_code == 403
    resp = declarant.post(url, {"assignee_id": str(me.id), "row_version": 1})
    assert resp.status_code == 200 and resp.json()["assigned_to"]["email"] == "declarant@a.test"
    # Déjà pris : le déclarant ne peut plus le réattribuer ; le validateur oui.
    assert declarant.post(url, {"assignee_id": str(me.id), "row_version": 2}).status_code == 403
    v = session("validateur@a.test")
    assert v.post(url, {"assignee_id": str(world["users"]["b_declarant"].id), "row_version": 2}).status_code == 422
    assert v.post(url, {"assignee_id": str(world["users"]["a_admin"].id), "row_version": 2}).status_code == 422
    assert v.post(url, {"assignee_id": str(validator.id), "row_version": 1}).status_code == 409
    assert v.post(url, {"assignee_id": str(validator.id), "row_version": 2}).status_code == 200
    assert AuditEvent.objects.filter(event_type="case.assigned").count() == 2


# --- Brouillon incomplet (T04, DOS-02, DOS-03) ----------------------------------------


def test_incomplete_draft_is_saved_and_lists_missing_per_line(world, editions, session):
    s = session("declarant@a.test")
    case = create_case(s)
    rev = case["revision"]["id"]
    eur = add_invoice(s, rev, currency="eur", declared_total="3100")
    usd = add_invoice(s, rev, supplier_name="Autre fournisseur", invoice_number="", currency="USD")
    add_line(s, eur["id"], customs_code="0101.10.00")
    add_line(s, usd["id"], origin_country="", quantity=None, description_raw="Viande fictive", amount="-10")
    detail = s.get(f"/api/v1/revisions/{rev}").json()
    assert [i["currency"] for i in detail["invoices"]] == ["EUR", "USD"]
    assert {ln["origin_country"] for i in detail["invoices"] for ln in i["lines"]} == {"FR", ""}
    blocking = {(b["scope"], b["field"], b["label"]) for b in detail["completeness"]["blocking"]}
    assert ("case", "importer", case["reference"]) in blocking
    assert ("revision", "target_edition", "Révision 1") in blocking
    assert ("invoice", "invoice_number", "Facture 2") in blocking
    assert ("invoice_line", "quantity", "Facture 2, ligne 1") in blocking
    assert ("invoice_line", "origin_country", "Facture 2, ligne 1") in blocking
    assert ("revision", "goods_lines", "Révision 1") in blocking
    messages = " ".join(w["message"] for w in detail["completeness"]["warnings"])
    assert "Somme des lignes 3000 ≠ total imprimé 3100 (écart 100)" in messages
    assert "Montant négatif" in messages
    assert "Aucune facture jointe" in messages
    assert detail["completeness"]["complete"] is False


# --- Codes : saisie et observations (T07, COD-01, EXT-04) -----------------------------


def test_code_kept_as_text_with_field_and_supplier_reference_apart(prepared):
    line = prepared["line"]
    assert line["source_reference"] == "12345678"
    [code] = line["codes"]
    assert (code["raw_code"], code["normalized_code"], code["field_label"], code["code_kind"]) == (
        "0101.10.00",
        "01011000",
        "HS Code",
        "customs",
    )
    resp = prepared["s"].post(f"/api/v1/invoices/{prepared['invoice']['id']}/lines", {"customs_code": 1011000})
    assert resp.status_code == 400


def test_changing_code_supersedes_observation_without_losing_it(prepared):
    s, line = prepared["s"], prepared["line"]
    resp = s.patch(f"/api/v1/invoice-lines/{line['id']}", {"customs_code": "0101.90.00", "row_version": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert [c["raw_code"] for c in body["codes"]] == ["0101.90.00"]
    assert [c["raw_code"] for c in body["code_history"]] == ["0101.10.00"]
    assert CodeObservation.objects.filter(invoice_line_id=line["id"]).count() == 2


# --- Contrôle et confirmation (T11, COD-02, COD-03, COD-07) ---------------------------


def test_present_code_recognized_then_confirmed_with_author(prepared, editions):
    s, goods = prepared["s"], prepared["goods"]
    result = check(s, goods["id"], editions["csv"])
    assert result["recognition_status"] == "recognized"
    assert result["normalized_code"] == "01011000" and result["node"]["code"] == "01011000"
    assert result["human_confirmation"] == "pending"
    assert result["operational_applicability"] == "unverified"
    codes = {f["code"]: f for f in result["findings"]}
    assert codes["HISTORICAL_REFERENCE"]["severity"] == "blocking_for_operational_calculation"
    assert "SUPPLIER_REFERENCE_NOT_CUSTOMS" in codes and "CONSISTENCY_RULES_NOT_ENCODED" in codes
    assert "SOURCE_ISSUE" in codes  # 01011000 est répété dans la source : l'anomalie reste visible

    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    body = {"action": "confirm", "code_check_id": result["id"], "goods_line_version": goods["row_version"]}
    assert s.post(url, body | {"reason": " "}).status_code == 400
    resp = s.post(url, body | {"reason": "Code de la facture conforme à la désignation."})
    assert resp.status_code == 201, resp.content
    decision = resp.json()["decision"]
    assert decision["selected_code"] == "01011000" and decision["actor"]["email"] == "declarant@a.test"
    assert decision["is_current"] is True
    assert resp.json()["latest_check"]["human_confirmation"] == "confirmed"
    assert AuditEvent.objects.filter(
        event_type="goods_line.code_decided", scope=f"case:{prepared['case']['id']}"
    ).exists()
    blocking = s.get(f"/api/v1/revisions/{prepared['rev']}").json()["completeness"]["blocking"]
    assert not [b for b in blocking if b["field"] == "code"]


def test_incomplete_code_lists_subdivisions_without_padding(prepared, editions):
    s = prepared["s"]
    line = add_line(s, prepared["invoice"]["id"], customs_code="0101")
    goods = add_goods(s, prepared["rev"], [line["id"]])
    result = check(s, goods["id"], editions["csv"])
    assert result["recognition_status"] == "incomplete"
    sub = next(f for f in result["findings"] if f["code"] == "SUBDIVISIONS_REQUIRED")["details"]["subdivisions"]
    assert [x["code"] for x in sub] == ["01011000", "01019000"]
    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    base = {"code_check_id": result["id"], "goods_line_version": goods["row_version"], "reason": "Subdivision choisie"}
    assert s.post(url, base | {"action": "confirm"}).status_code == 422
    other = editions["csv"].nodes.get(code="30049000")
    assert s.post(url, base | {"action": "complete", "node_id": str(other.id)}).status_code == 422
    target = editions["csv"].nodes.get(code="01019000")
    resp = s.post(url, base | {"action": "complete", "node_id": str(target.id)})
    assert resp.status_code == 201 and resp.json()["decision"]["selected_code"] == "01019000"
    # Le code observé reste celui de la facture.
    assert CodeObservation.objects.get(invoice_line_id=line["id"]).raw_code == "0101"


@pytest.mark.parametrize(
    ("data", "expected", "finding"),
    [
        ({"customs_code": "9999.99.99"}, "not_found", "CODE_NOT_FOUND"),
        ({"customs_code": "3004AB00"}, "not_found", "MALFORMED_CODE"),
        ({"source_reference": "30049000"}, "missing", "NO_CUSTOMS_CODE"),
        ({"uncertain_code": "30049000", "uncertain_code_label": "Réf."}, "ambiguous", "AMBIGUOUS_FIELD"),
        ({"customs_code": "0101.10.10"}, "edition_mismatch", "FOUND_IN_OTHER_EDITION"),
    ],
)
def test_check_states(prepared, editions, data, expected, finding):
    s = prepared["s"]
    line = add_line(s, prepared["invoice"]["id"], **data)
    goods = add_goods(s, prepared["rev"], [line["id"]])
    result = check(s, goods["id"], editions["csv"])
    assert result["recognition_status"] == expected
    assert finding in {f["code"] for f in result["findings"]}
    # Une référence fournisseur de huit chiffres n'est jamais prise pour un code douanier.
    if "source_reference" in data:
        assert result["observed_code"] is None


def test_conflicting_codes_on_grouped_lines_are_ambiguous(prepared, editions):
    s = prepared["s"]
    other = add_line(s, prepared["invoice"]["id"], customs_code="0101.90.00")
    second = add_line(s, prepared["invoice"]["id"], customs_code="0101.10.00")
    goods = add_goods(s, prepared["rev"], [other["id"], second["id"]])
    assert check(s, goods["id"], editions["csv"])["recognition_status"] == "ambiguous"
    assert (
        s.post(f"/api/v1/revisions/{prepared['rev']}/goods-lines", {"invoice_line_ids": [other["id"]]}).status_code
        == 409
    )


def test_replace_requires_evidence_and_keeps_original(prepared, editions):
    s, goods = prepared["s"], prepared["goods"]
    result = check(s, goods["id"], editions["csv"])
    node = editions["csv"].nodes.get(code="01019000")
    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    body = {"action": "replace", "node_id": str(node.id), "code_check_id": result["id"], "goods_line_version": 1}
    assert s.post(url, body | {"reason": "Désignation non reproductrice"}).status_code == 400
    resp = s.post(url, body | {"reason": "Désignation non reproductrice", "evidence_refs": ["Fiche technique p. 2"]})
    assert resp.status_code == 201
    decision = ClassificationDecision.objects.get()
    assert decision.original_observation.raw_code == "0101.10.00" and decision.selected_code == "01019000"


# --- Concurrence et invalidation (T33, WF-03) ------------------------------------------


def test_two_users_edit_same_revision(prepared, session):
    other = session("validateur@a.test")
    url = f"/api/v1/revisions/{prepared['rev']}"
    assert prepared["s"].patch(url, {"regime": "C200", "row_version": 1}).status_code == 200
    resp = other.patch(url, {"regime": "C300", "row_version": 1})
    assert resp.status_code == 409 and resp.json()["code"] == "REVISION_CONFLICT"
    assert resp.json()["details"] == {"expected_version": 1, "current_version": 2}
    assert other.get(url).json()["regime"] == "C200"
    assert other.patch(url, {"regime": "C300"}).status_code == 400


def test_decision_on_stale_check_or_version_is_refused(prepared, editions, session):
    s, goods = prepared["s"], prepared["goods"]
    result = check(s, goods["id"], editions["csv"])
    s.patch(f"/api/v1/invoice-lines/{prepared['line']['id']}", {"customs_code": "0101.90.00", "row_version": 1})
    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    body = {"action": "confirm", "code_check_id": result["id"], "goods_line_version": 1, "reason": "ok"}
    resp = s.post(url, body)
    assert resp.status_code == 409 and resp.json()["code"] == "CODE_CHECK_STALE"

    fresh = check(s, goods["id"], editions["csv"])
    other = session("validateur@a.test")
    assert s.post(url, body | {"code_check_id": fresh["id"]}).status_code == 201
    resp = other.post(url, body | {"code_check_id": fresh["id"]})
    assert resp.status_code == 409 and resp.json()["code"] == "REVISION_CONFLICT"
    assert ClassificationDecision.objects.count() == 1


def test_data_change_after_decision_requires_review(prepared, editions):
    s, goods = prepared["s"], prepared["goods"]
    result = check(s, goods["id"], editions["csv"])
    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    s.post(url, {"action": "confirm", "code_check_id": result["id"], "goods_line_version": 1, "reason": "ok"})
    resp = s.patch(f"/api/v1/goods-lines/{goods['id']}", {"description": "Juments fictives", "row_version": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"]["is_current"] is False and body["latest_check"]["human_confirmation"] == "stale"
    blocking = s.get(f"/api/v1/revisions/{prepared['rev']}").json()["completeness"]["blocking"]
    assert any(b["field"] == "code" and "à revoir" in b["message"] for b in blocking)


def test_validated_revision_is_read_only(prepared):
    s = prepared["s"]
    resp = s.post(f"/api/v1/cases/{prepared['case']['id']}/revisions", {"reason": "x"})
    assert resp.status_code == 409 and resp.json()["code"] == "REVISION_NOT_VALIDATED"
    CaseRevision.objects.filter(pk=prepared["rev"]).update(state=CaseRevision.State.VALIDATED)
    resp = s.patch(f"/api/v1/revisions/{prepared['rev']}", {"regime": "X", "row_version": 1})
    assert resp.status_code == 409 and resp.json()["code"] == "REVISION_NOT_EDITABLE"
    assert s.post(f"/api/v1/invoices/{prepared['invoice']['id']}/lines", {}).status_code == 409


def test_target_edition_must_be_published_and_not_withdrawn(world, editions, session):
    from apps.tariffs.services import withdraw_edition

    manager = User.objects.get(email="ref@test.test")
    withdraw_edition(edition=editions["text"], actor=manager, reason="test")
    s = session("declarant@a.test")
    assert s.post("/api/v1/cases", {"target_edition_id": str(editions["text"].id)}).status_code == 422


# --- Isolation (T01, ACC-02, AUD-02) ---------------------------------------------------


def test_other_organization_cannot_reach_anything(prepared, editions, session):
    b = session("declarant@b.test")
    case_id, rev, goods = prepared["case"]["id"], prepared["rev"], prepared["goods"]["id"]
    inv, line = prepared["invoice"]["id"], prepared["line"]["id"]
    attempts = [
        b.get(f"/api/v1/cases/{case_id}"),
        b.patch(f"/api/v1/cases/{case_id}", {"title": "x", "row_version": 1}),
        b.post(f"/api/v1/cases/{case_id}/assign", {"assignee_id": None, "row_version": 1}),
        b.get(f"/api/v1/cases/{case_id}/audit"),
        b.get(f"/api/v1/cases/{case_id}/documents"),
        b.get(f"/api/v1/revisions/{rev}"),
        b.patch(f"/api/v1/revisions/{rev}", {"regime": "x", "row_version": 1}),
        b.post(f"/api/v1/revisions/{rev}/invoices", {}),
        b.post(f"/api/v1/revisions/{rev}/goods-lines", {"invoice_line_ids": [line]}),
        b.patch(f"/api/v1/invoices/{inv}", {"currency": "XAF", "row_version": 1}),
        b.post(f"/api/v1/invoices/{inv}/lines", {}),
        b.patch(f"/api/v1/invoice-lines/{line}", {"customs_code": "1", "row_version": 1}),
        b.get(f"/api/v1/goods-lines/{goods}"),
        b.post(f"/api/v1/goods-lines/{goods}/code-checks", {"edition_id": str(editions["csv"].id)}),
        b.get(f"/api/v1/goods-lines/{goods}/decisions"),
    ]
    for resp in attempts:
        assert resp.status_code == 404, (resp.request["PATH_INFO"], resp.status_code)
        assert prepared["case"]["reference"] not in resp.content.decode()
    assert b.get("/api/v1/cases").json()["results"] == []
    # B se crée un dossier : il ne peut pas y rattacher une ligne de A.
    b_case = create_case(b)
    resp = b.post(f"/api/v1/revisions/{b_case['revision']['id']}/goods-lines", {"invoice_line_ids": [line]})
    assert resp.status_code == 422


def test_case_audit_lists_only_this_case(prepared, session):
    s = prepared["s"]
    other = create_case(s)
    events = s.get(f"/api/v1/cases/{prepared['case']['id']}/audit").json()["results"]
    types = {e["event_type"] for e in events}
    assert {
        "case.created",
        "invoice.created",
        "invoice_line.created",
        "invoice_line.code_observed",
        "goods_line.created",
    } <= types
    assert all(e["entity_id"] != other["id"] for e in events)
    # Aucun texte de facture n'est recopié dans le journal.
    assert "Chevaux reproducteurs fictifs" not in str(events)


def test_deactivated_member_loses_access(prepared, session):
    Membership.objects.filter(user__email="declarant@a.test").update(active=False)
    resp = prepared["s"].get(f"/api/v1/cases/{prepared['case']['id']}")
    assert resp.status_code == 403
    assert Membership.objects.filter(user__email="validateur@a.test", roles__contains=[Role.VALIDATOR]).exists()


def test_preparation_fields_on_creation_and_update(world, session):
    """Écran « Nouveau dossier » : transport, bureau, pays et priorité restent vides tant qu'ils sont inconnus."""
    s = session("declarant@a.test")
    blank = create_case(s)["revision"]
    assert blank["transport_mode"] == "" and blank["origin_country"] == "" and blank["priority"] == "normal"
    case = create_case(
        s,
        client_reference="NIF-0001",
        transport_mode="sea",
        entry_office="Port d'Owendo",
        origin_country="cn",
        provenance_country="CN",
        priority="high",
    )
    rev = case["revision"]
    assert rev["transport_mode_label"] == "Maritime" and rev["origin_country"] == "CN"
    assert rev["entry_office"] == "Port d'Owendo" and rev["priority_label"] == "Haute"
    resp = s.patch(f"/api/v1/revisions/{rev['id']}", {"transport_mode": "air", "origin_country": "", "row_version": 1})
    assert resp.status_code == 200, resp.content
    assert resp.json()["transport_mode"] == "air" and resp.json()["origin_country"] == ""
    assert s.post("/api/v1/cases", {"origin_country": "Chine"}).status_code == 400
    assert s.post("/api/v1/cases", {"transport_mode": "teleport"}).status_code == 400
    event = AuditEvent.objects.filter(event_type="revision.updated").latest("at")
    assert event.current["transport_mode"] == "air"
