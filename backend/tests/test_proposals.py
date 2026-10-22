"""Lot 3, aide au classement sans IA : COD-03 à COD-06, DEV-018, DEV-019, T01 sur les propositions.

Référentiel fictif (fixtures/synthetic/referentiel-lot3.csv) ; aucune IA n'est raccordée.
"""

import pytest

from apps.extraction import ai, synthetic
from tests.test_extraction import extracted, make_case, make_edition, only_invoice


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def edition(db):
    return make_edition()


@pytest.fixture
def case(world, edition, session):
    return make_case(session, edition)


def manual_goods(case, **line):
    s = case["s"]
    inv = s.post(
        f"/api/v1/revisions/{case['revision']}/invoices",
        {
            "supplier_name": "Fournisseur fictif",
            "invoice_number": "M-1",
            "invoice_date": "2026-09-01",
            "currency": "EUR",
        },
    ).json()
    body = {"description_raw": "Selles en cuir fictives", "quantity": "1", "unit_price": "10", "amount": "10"}
    resp = s.post(f"/api/v1/invoices/{inv['id']}/lines", body | line)
    assert resp.status_code == 201, resp.content
    resp = s.post(f"/api/v1/revisions/{case['revision']}/goods-lines", {"invoice_line_ids": [resp.json()["id"]]})
    assert resp.status_code == 201, resp.content
    return resp.json()


def check(case, goods, edition):
    resp = case["s"].post(f"/api/v1/goods-lines/{goods['id']}/code-checks", {"edition_id": str(edition.id)})
    assert resp.status_code == 201, resp.content
    return resp.json()


def propose(case, goods, **data):
    return case["s"].post(f"/api/v1/goods-lines/{goods['id']}/proposals", data)


def assert_in_edition(proposals, edition):
    for p in proposals:
        node = edition.nodes.get(pk=p["node_id"])
        assert node.declarable and node.code == p["code"] and p["reasons"]


def test_recognized_code_takes_the_short_path_and_needs_no_proposal(case, edition):
    goods = manual_goods(case, customs_code="4201.00.00")
    resp = propose(case, goods)
    assert resp.status_code == 409 and resp.json()["code"] == "PROPOSALS_NOT_NEEDED"
    # Sur demande explicite seulement, d'autres pistes sont listées, le code présent restant affiché.
    resp = propose(case, goods, explicit=True)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["trigger"] == "explicit" and body["is_ai"] is False and body["producer"].startswith("recherche")
    assert_in_edition(body["proposals"], edition)


def test_incomplete_code_proposes_its_subdivisions_without_padding(case, edition):
    goods = manual_goods(case, description_raw="Chevaux reproducteurs fictifs", customs_code="0101")
    body = propose(case, goods).json()
    assert body["trigger"] == "incomplete"
    codes = [p["code"] for p in body["proposals"]]
    assert codes[:2] == ["01012100", "01012900"]
    assert "Subdivision du code présent « 0101 »." in body["proposals"][0]["reasons"]
    assert any("subdivision" in q for q in body["questions"])
    # Les libellés qui distinguent les deux subdivisions sont donnés, pas tranchés.
    assert {d["code"] for d in body["proposals"][0]["distinguishing"]} >= {"01012900"}
    assert_in_edition(body["proposals"], edition)
    assert "0101000" not in codes and "01010000" not in codes


def test_missing_code_gets_reasoned_proposals_then_a_traced_classification(case, edition):
    goods = manual_goods(case, description_raw="Tapis de selle fictifs")
    result = check(case, goods, edition)
    assert result["recognition_status"] == "missing"
    body = propose(case, goods).json()
    assert body["trigger"] == "missing" and body["is_current"] is True
    first = body["proposals"][0]
    assert first["code"] == "42010000" and "tapis" in first["reasons"][0]
    assert_in_edition(body["proposals"], edition)

    url = f"/api/v1/goods-lines/{goods['id']}/decisions"
    base = {"action": "classify", "code_check_id": result["id"], "reason": "Tapis de selle : article de sellerie."}
    goods_version = case["s"].get(f"/api/v1/goods-lines/{goods['id']}").json()["row_version"]
    other = edition.nodes.get(code="96039000")
    wrong = base | {"node_id": str(other.id), "proposal_id": first["id"], "goods_line_version": goods_version}
    resp = case["s"].post(url, wrong)
    assert resp.status_code == 422 and resp.json()["code"] == "INVALID_PROPOSAL"
    resp = case["s"].post(
        url, base | {"node_id": first["node_id"], "proposal_id": first["id"], "goods_line_version": goods_version}
    )
    assert resp.status_code == 201, resp.content
    decision = resp.json()["decision"]
    assert decision["selected_code"] == "42010000" and decision["actor"]["email"] == "declarant@a.test"
    assert {"proposal_id": first["id"], "producer": body["producer"]} in decision["evidence_refs"]
    # Classer n'est pas accepter en douane : la décision reste interne.
    assert case["s"].get(f"/api/v1/revisions/{case['revision']}").json()["state"] == "draft"


def test_classify_is_refused_when_a_code_is_present(case, edition):
    goods = manual_goods(case, customs_code="4201.00.00")
    result = check(case, goods, edition)
    node = edition.nodes.get(code="42010000")
    resp = case["s"].post(
        f"/api/v1/goods-lines/{goods['id']}/decisions",
        {
            "action": "classify",
            "code_check_id": result["id"],
            "node_id": str(node.id),
            "reason": "x",
            "goods_line_version": goods["row_version"],
        },
    )
    assert resp.status_code == 422 and resp.json()["code"] == "CANNOT_CLASSIFY"


def test_nothing_matching_gives_questions_not_invented_codes(case, edition):
    goods = manual_goods(case, description_raw="Zxqwv ploutre")
    body = propose(case, goods).json()
    assert body["proposals"] == []
    assert any("préciser" in q for q in body["questions"])
    assert "De quelle matière la marchandise est-elle faite ?" in body["questions"]


def test_proposals_become_stale_when_the_goods_change(case, edition):
    goods = manual_goods(case, description_raw="Brosses pour chevaux")
    body = propose(case, goods).json()
    assert "96032900" in [p["code"] for p in body["proposals"]]
    resp = case["s"].patch(
        f"/api/v1/goods-lines/{goods['id']}", {"description": "Balais fictifs", "row_version": goods["row_version"]}
    )
    assert resp.status_code == 200, resp.content
    [listed] = case["s"].get(f"/api/v1/goods-lines/{goods['id']}/proposals").json()["results"]
    assert listed["id"] == body["id"] and listed["is_current"] is False


def test_short_path_after_extraction_goods_lines_then_confirm(case, edition):
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    invoice = only_invoice(case)
    resp = case["s"].post(f"/api/v1/invoices/{invoice['id']}/goods-lines", {})
    assert resp.status_code == 201, resp.content
    goods = resp.json()["results"]
    assert [g["description"] for g in goods] == ["Chevaux reproducteurs fictifs", "Selles en cuir fictives"]
    # Une seconde demande ne duplique rien : les lignes sont déjà rattachées.
    assert case["s"].post(f"/api/v1/invoices/{invoice['id']}/goods-lines", {}).json()["results"] == []
    result = check(case, goods[0], edition)
    assert result["recognition_status"] == "recognized" and result["observed_code"] == "0101.21.00"
    resp = case["s"].post(
        f"/api/v1/goods-lines/{goods[0]['id']}/decisions",
        {
            "action": "confirm",
            "code_check_id": result["id"],
            "reason": "Code de la facture conforme.",
            "goods_line_version": case["s"].get(f"/api/v1/goods-lines/{goods[0]['id']}").json()["row_version"],
        },
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["decision"]["selected_code"] == "01012100"


def test_other_company_cannot_read_request_or_use_proposals(case, edition, session):
    goods = manual_goods(case, description_raw="Tapis de selle fictifs")
    result = check(case, goods, edition)
    proposal = propose(case, goods).json()["proposals"][0]
    invoice = only_invoice(case)
    b = session("declarant@b.test")
    assert b.get(f"/api/v1/goods-lines/{goods['id']}/proposals").status_code == 404
    assert b.post(f"/api/v1/goods-lines/{goods['id']}/proposals", {}).status_code == 404
    assert b.post(f"/api/v1/invoices/{invoice['id']}/goods-lines", {}).status_code == 404
    resp = b.post(
        f"/api/v1/goods-lines/{goods['id']}/decisions",
        {
            "action": "classify",
            "code_check_id": result["id"],
            "node_id": proposal["node_id"],
            "proposal_id": proposal["id"],
            "reason": "x",
            "goods_line_version": 1,
        },
    )
    assert resp.status_code == 404


# --- DEV-019 : IA non raccordée, sorties contrôlées ----------------------------------------


def test_ai_is_disabled_and_refuses_explicitly(settings):
    assert settings.AI_PROVIDER == "disabled" and ai.is_enabled() is False
    provider = ai.get_provider()
    with pytest.raises(ai.AIUnavailable):
        provider.rank_candidates(description="Selles", candidates=[])
    settings.AI_PROVIDER = "inconnu"
    with pytest.raises(ai.AIUnavailable):
        ai.get_provider()  # pas de repli silencieux vers un autre fournisseur


def test_ai_output_with_invented_code_or_missing_citation_is_rejected():
    allowed = {"n1": "42010000", "n2": "96032900"}
    output = [
        {"node_id": "n1", "code": "42010000", "citations": ["note-42"]},
        {"node_id": "n9", "code": "42019999", "citations": ["note-42"]},
        {"node_id": "n2", "code": "96030000", "citations": ["note-96"]},
        {"node_id": "n2", "code": "96032900", "citations": []},
        {"node_id": "n2", "code": "96032900", "citations": ["source-inventee"]},
        "texte libre",
    ]
    accepted, rejected = ai.validate_ranking(output, allowed=allowed, sources={"note-42", "note-96"})
    assert accepted == [{"node_id": "n1", "code": "42010000", "citations": ["note-42"]}]
    assert [r.index for r in rejected] == [1, 2, 3, 4, 5]
    assert "inventé" in rejected[0].reason and "Preuve" in rejected[2].reason


def test_unknown_code_is_kept_and_codes_with_the_same_start_are_proposed(case, edition):
    goods = manual_goods(case, customs_code="4201.99.99")
    body = propose(case, goods).json()
    assert body["trigger"] == "not_found"
    first = body["proposals"][0]
    assert first["code"] == "42010000" and "Même début" in first["reasons"][0] and "4201.99.99" in first["reasons"][0]
    # Le code de la facture reste celui observé : rien n'est substitué.
    line = only_invoice(case)["lines"][0]
    assert [c["raw_code"] for c in line["codes"]] == ["4201.99.99"]
