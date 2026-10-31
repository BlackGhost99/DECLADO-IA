"""T80 : l'IA choisit le code parmi les propositions du référentiel (CLA-IA).

Aucun appel réel : un fournisseur factice remplace l'adaptateur. Référentiel fictif.
"""

import pytest

from apps.cases.models import AIClassification, ClassificationDecision
from apps.clients.models import Importer
from apps.extraction import ai, synthetic
from apps.extraction.models import OrganizationAISettings
from tests.test_extraction import extracted, make_case, make_edition
from tests.test_proposals import check, manual_goods


class FakeChooser:
    name, model = "anthropic", "claude-haiku-5-5"

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def choose_code(self, *, description, candidates):
        self.calls.append({"description": description, "candidates": candidates})
        answer = self.answer(candidates) if callable(self.answer) else self.answer
        return ai.Completion(items=[answer], model=self.model, input_tokens=400, output_tokens=60)


def pick(code):
    def answer(candidates):
        chosen = next(c for c in candidates if c["code"].replace(".", "") == code)
        return {"found": True, "node_id": chosen["node_id"], "code": chosen["code"],
                "evidence": "reproducteurs", "reason": "Reproducteurs de race pure : première ligne."}  # fmt: skip

    return answer


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def edition(db):
    return make_edition()


@pytest.fixture
def case(world, edition, session):
    return make_case(session, edition)


@pytest.fixture
def ai_on(world, settings, monkeypatch):
    settings.AI_PROVIDER, settings.AI_API_KEY, settings.AI_FREE_TIER = "anthropic", "cle-de-test", False
    OrganizationAISettings.objects.create(organization=world["org_a"], enabled=True)
    holder = {"provider": FakeChooser(pick("01012100"))}
    monkeypatch.setattr(ai, "get_provider", lambda: holder["provider"])
    return holder


def ask_ai(case, goods):
    return case["s"].post(f"/api/v1/goods-lines/{goods['id']}/ai-choice", {})


def test_ai_picks_one_of_the_proposals_and_the_agent_keeps_it(case, edition, ai_on):
    goods = manual_goods(case, description_raw="Chevaux reproducteurs fictifs", customs_code="0101")
    result = check(case, goods, edition)
    resp = ask_ai(case, goods)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    choice = body["ai_choice"]
    assert choice["code"] == "01012100" and choice["status"] == "sent" and choice["evidence"] == "reproducteurs"
    assert body["ai_available"] is True
    # Seules la désignation et les lignes candidates sont parties : ni client, ni montant, ni pièce.
    [call] = ai_on["provider"].calls
    assert call["description"] == "Chevaux reproducteurs fictifs"
    assert {c["code"] for c in call["candidates"]} >= {"0101.21.00", "0101.29.00"}
    assert "Importateur" not in str(call) and "10" not in call["description"]
    # L'agent retient le choix : décision humaine motivée, qui garde la trace de l'IA.
    goods_now = case["s"].get(f"/api/v1/goods-lines/{goods['id']}").json()
    resp = case["s"].post(
        f"/api/v1/goods-lines/{goods['id']}/decisions",
        {"action": "complete", "code_check_id": result["id"], "node_id": choice["node_id"],
         "proposal_id": choice["proposal_id"], "reason": "Choix de l'IA vérifié.",
         "goods_line_version": goods_now["row_version"]},
    )  # fmt: skip
    assert resp.status_code == 201, resp.content
    decision = ClassificationDecision.objects.get()
    assert decision.selected_code == "01012100" and decision.actor.email == "declarant@a.test"
    assert {"kind": "ai_choice", "ai_choice_id": choice["id"], "model": "claude-haiku-5-5"} in decision.evidence_refs


def test_invented_code_or_unfounded_quote_is_rejected_never_repaired(case, edition, ai_on):
    goods = manual_goods(case, description_raw="Chevaux reproducteurs fictifs", customs_code="0101")
    check(case, goods, edition)
    ai_on["provider"] = FakeChooser(
        {
            "found": True,
            "node_id": "00000000-0000-0000-0000-000000000000",
            "code": "01019999",
            "evidence": "reproducteurs",
            "reason": "x",
        }  # fmt: skip
    )
    choice = ask_ai(case, goods).json()["ai_choice"]
    assert choice["code"] is None and choice["insufficient"] is False
    assert "inventé" in choice["rejected"][0]["reason"]
    ai_on["provider"] = FakeChooser(
        lambda c: {
            "found": True,
            "node_id": c[0]["node_id"],
            "code": c[0]["code"],
            "evidence": "pur-sang arabe",
            "reason": "x",
        }  # fmt: skip
    )
    choice = ask_ai(case, goods).json()["ai_choice"]
    assert choice["code"] is None and "introuvable" in choice["rejected"][0]["reason"]


def test_insufficient_information_is_an_accepted_answer(case, edition, ai_on):
    goods = manual_goods(case, description_raw="Chevaux fictifs", customs_code="0101")
    check(case, goods, edition)
    ai_on["provider"] = FakeChooser(
        {"found": False, "node_id": "", "code": "", "evidence": "", "reason": "Race pure ou non : non précisé."}
    )
    choice = ask_ai(case, goods).json()["ai_choice"]
    assert choice["insufficient"] is True and choice["code"] is None and "non précisé" in choice["reason"]


def test_client_refusal_and_disabled_company_send_nothing(case, edition, ai_on, world):
    goods = manual_goods(case, description_raw="Chevaux reproducteurs fictifs", customs_code="0101")
    check(case, goods, edition)
    importer = world["importer_a"]
    Importer.objects.filter(pk=importer.pk).update(ai_refused=True)
    s = case["s"]
    detail = s.get(f"/api/v1/cases/{case['id']}").json()
    assert (
        s.patch(
            f"/api/v1/cases/{case['id']}", {"importer_id": str(importer.id), "row_version": detail["row_version"]}
        ).status_code
        == 200
    )
    choice = ask_ai(case, goods).json()["ai_choice"]
    assert choice["status"] == "client_refused" and ai_on["provider"].calls == []
    OrganizationAISettings.objects.filter(organization=world["org_a"]).update(enabled=False)
    resp = ask_ai(case, goods)
    assert resp.status_code == 409 and resp.json()["code"] == "AI_NOT_ENABLED"


def test_reading_asks_the_ai_automatically_for_codes_to_settle(world, session, ai_on):
    edition = make_edition()
    case = make_case(session, edition)
    lines = [dict(synthetic.SIMPLE_LINES[0], code="0101")]
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf(lines, total=None))
    [choice] = AIClassification.objects.all()
    assert choice.trigger == "auto" and choice.chosen.code == "01012100"
    goods = case["s"].get(f"/api/v1/revisions/{case['revision']}").json()["goods_lines"]
    assert goods[0]["latest_check"]["recognition_status"] == "incomplete"
    assert goods[0]["decision"] is None  # l'IA ne décide jamais


def test_journal_is_append_only_and_other_company_cannot_ask(case, edition, ai_on, session):
    goods = manual_goods(case, description_raw="Chevaux reproducteurs fictifs", customs_code="0101")
    check(case, goods, edition)
    ask_ai(case, goods)
    choice = AIClassification.objects.get()
    with pytest.raises(ValueError):
        choice.save()
    assert ask_ai({"s": session("declarant@b.test")}, goods).status_code == 404
