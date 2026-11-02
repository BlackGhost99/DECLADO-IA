# ruff: noqa: F811  (fixtures importées)
"""Exonérations (TAX-04, T23, T94 à T96), sur des données fictives.

Déclarées par l'admin ClairTransit avec leur texte, demandées dans le dossier, appliquées
seulement après validation du justificatif et dans leur champ d'application.
"""

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.documents.synthetic import make_pdf
from apps.fiscal.models import ExemptionClaim
from tests.test_fiscal import _private_storage, confirm, edition, manager, schedule  # noqa: F401
from tests.test_supervision import clean, fake_scanner
from tests.test_validation import act, complete, ready_case

REGIME = {
    "code": "EXO-FICTIF-1",
    "label": "Exonération fictive d'essai",
    "conditions": "Attestation fictive d'essai.",
    "taxes": {"DDI": "0", "TVA": "0"},
    "hs_prefixes": "4201",
    "required_documents": ["Attestation d'exonération (fictive)"],
    "valid_from": "2026-01-01",
    "source_kind": "operator",
    "source_reference": "",
    "reason": "Essai fictif : aucun texte officiel.",
}


def declare(s, **data):
    return s.post("/api/v1/fiscal/exemptions", REGIME | data)


def setup_case(world, edition, session, monkeypatch, manager, **regime):
    regime = declare(session(manager.email), **regime)
    assert regime.status_code == 201, regime.content
    case, _ = ready_case(session, edition, email="declarant@a.test")
    complete(case, world, edition)
    fake_scanner(monkeypatch, clean)
    file = SimpleUploadedFile("attestation.pdf", make_pdf(["Attestation fictive"]), content_type="application/pdf")
    proof = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "usage": "other"})
    assert proof.status_code == 201, proof.content
    return case, regime.json(), proof.json()["id"]


def taxes_of(case):
    calc = case["s"].get(f"/api/v1/cases/{case['id']}/calculation").json()
    return calc, {t["code"]: t for t in calc["articles"][0]["taxes"]}


def test_t94_only_the_platform_admin_declares_an_exemption_with_its_scope_and_text(world, manager, session):
    assert declare(session("admin@a.test")).status_code == 403
    s = session(manager.email)
    assert declare(s, required_documents=[]).json()["details"]["field"] == "required_documents"
    assert declare(s, taxes={}).status_code == 400
    assert declare(s, taxes={"RI": "0"}).status_code == 400  # calculée par SYDONIA
    assert declare(s, hs_prefixes="42A").status_code == 400
    assert declare(s, source_kind="finance_law").json()["details"]["field"] == "source_reference"
    assert declare(s, reason="").status_code == 400
    created = declare(s)
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["taxes"] == {"DDI": "0", "TVA": "0"} and body["hs_prefixes"] == ["4201"]
    assert body["official"] is False  # aucun texte : jamais présentée comme réglementaire
    assert declare(s).status_code == 409  # même référence encore active
    listed = session("declarant@a.test").get("/api/v1/fiscal/exemptions?active=1").json()
    assert [r["code"] for r in listed["results"]] == ["EXO-FICTIF-1"] and listed["can_edit"] is False

    url = f"/api/v1/fiscal/exemptions/{body['id']}/deactivate"
    assert session("admin@a.test").post(url, {"reason": "x"}).status_code == 403
    assert s.post(url, {"reason": " "}).status_code == 400
    assert s.post(url, {"reason": "Texte abrogé (essai fictif)."}).json()["is_active"] is False
    assert session("declarant@a.test").get("/api/v1/fiscal/exemptions?active=1").json()["results"] == []
    assert declare(s).status_code == 201  # nouvelle version après désactivation
    assert AuditEvent.objects.filter(event_type__startswith="fiscal.exemption_").count() == 3


def test_t23_exemption_waits_for_a_validated_proof_then_applies(
    world, schedule, edition, session, monkeypatch, manager
):
    case, regime, proof_id = setup_case(world, edition, session, monkeypatch, manager)
    s = case["s"]
    url = f"/api/v1/cases/{case['id']}/exemptions"
    claim = s.post(url, {"regime_id": regime["id"], "proof_reference": "ATT-FICTIVE-1"})
    assert claim.status_code == 201, claim.content
    claim = claim.json()
    assert s.post(url, {"regime_id": regime["id"]}).status_code == 409

    # Demandée sans preuve validée : rien n'est appliqué, calcul provisoire, soumission bloquée.
    calc, taxes = taxes_of(case)
    assert taxes["DDI"]["amount"] == "54907" and taxes["DDI"]["rate_status"] == "known"
    assert calc["provisional"] and any("Exonération demandée" in r for r in calc["provisional_reasons"])
    detail = s.get(f"/api/v1/cases/{case['id']}").json()
    assert [b["scope"] for b in detail["revision"]["completeness"]["blocking"]] == ["exemption"]
    assert act(case, "submit", detail["revision"]["row_version"]).json()["code"] == "SUBMISSION_BLOCKED"

    validator = session("validateur@a.test")
    decide = f"{url}/{claim['id']}"
    resp = validator.post(f"{decide}/validate", {"row_version": claim["row_version"]})
    assert resp.status_code == 409 and resp.json()["code"] == "PROOF_REQUIRED"
    claim = s.patch(decide, {"proof_ids": [proof_id], "row_version": claim["row_version"]}).json()
    assert claim["proof_ids"] == [proof_id]
    assert s.post(f"{decide}/validate", {"row_version": claim["row_version"]}).status_code == 403  # déclarant
    resp = validator.post(f"{decide}/validate", {"row_version": claim["row_version"]})
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "validated" and resp.json()["decided_by"] == "validateur"

    calc, taxes = taxes_of(case)
    ddi, tva = taxes["DDI"], taxes["TVA"]
    assert (ddi["amount"], ddi["rate"], ddi["rate_status"], ddi["schedule_rate"]) == ("0", "0", "exempted", "10")
    assert ddi["exemption"]["code"] == "EXO-FICTIF-1" and ddi["exemption"]["proof_reference"] == "ATT-FICTIVE-1"
    assert (tva["base"], tva["amount"]) == ("549070", "0")  # base sans DDI, exonérée elle aussi
    assert taxes["CCI"]["rate_status"] == "known"  # les autres taxes restent dues
    assert calc["articles"][0]["exemptions"]["applied"] == ["EXO-FICTIF-1"]
    detail = s.get(f"/api/v1/cases/{case['id']}").json()
    assert detail["revision"]["completeness"]["blocking"] == []
    assert act(case, "submit", detail["revision"]["row_version"]).status_code == 200
    assert AuditEvent.objects.filter(event_type__startswith="exemption.").count() == 3


def test_t95_out_of_scope_exemption_is_not_applied_and_says_why(
    world, schedule, edition, session, monkeypatch, manager
):
    case, regime, proof_id = setup_case(world, edition, session, monkeypatch, manager, hs_prefixes=["0101"])
    url = f"/api/v1/cases/{case['id']}/exemptions"
    claim = case["s"].post(url, {"regime_id": regime["id"], "proof_ids": [proof_id]}).json()
    validator = session("validateur@a.test")
    assert validator.post(f"{url}/{claim['id']}/validate", {"row_version": claim["row_version"]}).status_code == 200
    calc, taxes = taxes_of(case)
    assert taxes["DDI"]["amount"] == "54907" and "exemption" not in taxes["DDI"]
    [note] = calc["articles"][0]["exemptions"]["notes"]
    assert "non appliquée" in note and "hors des codes couverts" in note


def test_t96_reject_needs_a_reason_withdraw_and_other_companies_see_nothing(
    world, schedule, edition, session, monkeypatch, manager
):
    case, regime, proof_id = setup_case(world, edition, session, monkeypatch, manager)
    url = f"/api/v1/cases/{case['id']}/exemptions"
    claim = case["s"].post(url, {"regime_id": regime["id"], "proof_ids": [proof_id]}).json()
    other = session("declarant@b.test")
    assert other.get(url).status_code == 404
    assert other.post(url, {"regime_id": regime["id"]}).status_code == 404
    assert other.post(f"{url}/{claim['id']}/withdraw", {"row_version": claim["row_version"]}).status_code == 404

    validator = session("validateur@a.test")
    assert validator.post(f"{url}/{claim['id']}/reject", {"row_version": claim["row_version"]}).status_code == 400
    reason = "Attestation expirée (fictif)."
    rejected = validator.post(f"{url}/{claim['id']}/reject", {"row_version": claim["row_version"], "reason": reason})
    assert rejected.json()["status"] == "rejected"
    # Refusée : plus d'attente, une nouvelle demande reste possible, puis se retire.
    again = case["s"].post(url, {"regime_id": regime["id"]}).json()
    withdrawn = case["s"].post(f"{url}/{again['id']}/withdraw", {"row_version": again["row_version"]})
    assert withdrawn.json()["status"] == "withdrawn"
    assert ExemptionClaim.objects.filter(status="requested").count() == 0
    assert [c["status"] for c in case["s"].get(url).json()["results"]] == ["rejected", "withdrawn"]


def test_t100_exports_list_applied_exemptions_and_the_declared_lodging(
    world, schedule, edition, session, monkeypatch, manager
):
    import io

    from openpyxl import load_workbook

    from tests.test_exports import export, pdf_text

    case, regime, proof_id = setup_case(world, edition, session, monkeypatch, manager)
    url = f"/api/v1/cases/{case['id']}/exemptions"
    claim = case["s"].post(url, {"regime_id": regime["id"], "proof_ids": [proof_id], "proof_reference": "ATT-9"})
    claim = claim.json()
    validator = {**case, "s": session("validateur@a.test")}
    assert (
        validator["s"].post(f"{url}/{claim['id']}/validate", {"row_version": claim["row_version"]}).status_code == 200
    )
    rev = case["s"].get(f"/api/v1/cases/{case['id']}").json()["revision"]
    rev = act(case, "submit", rev["row_version"]).json()["revision"]
    rev = act(validator, "validate", rev["row_version"]).json()["revision"]
    lodged = act(case, "lodge", rev["row_version"], number="L 1234", lodged_on="2026-11-02")
    assert lodged.status_code == 200, lodged.content

    _, raw = export(case, "xlsx")
    wb = load_workbook(io.BytesIO(raw))
    sheet = wb["Exonérations appliquées"]
    assert [c.value for c in sheet[2]][:4] == [
        "EXO-FICTIF-1",
        "Exonération fictive d'essai",
        "DDI 0 % au lieu de 10 % ; TVA 0 % au lieu de 18 %",
        "1",
    ]
    assert sheet["F2"].value == "ATT-9"
    meta = {r[0].value: r[1].value for r in wb["Métadonnées"].iter_rows(min_row=2) if r[0].value}
    assert meta["Déposé en douane (saisi par l'agent)"].startswith("Déclaration n° L 1234 du 2026-11-02")
    _, raw = export(case, "pdf")
    text = pdf_text(raw)
    assert "Exonérations appliquées" in text and "EXO-FICTIF-1" in text and "L 1234" in text
