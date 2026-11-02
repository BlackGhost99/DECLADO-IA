# ruff: noqa: F811  (fixtures importées de test_fiscal)
"""Confirmation groupée des codes (T77, tout ou rien) et archive complète du dossier (EXP-04, T84).

Données fictives. Une révision validée l'est en interne, jamais acceptée par la Douane.
"""

import hashlib
import io
import json
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.cases.archive import _safe_name
from apps.cases.models import CaseExport, ClassificationDecision
from apps.documents.synthetic import make_pdf
from tests.test_extraction import make_case
from tests.test_fiscal import _private_storage, edition, goods_with_code, schedule  # noqa: F401
from tests.test_validation import act, complete, ready_case

PIECE = make_pdf(["FACTURE FICTIVE F-1", "Selles fictives  HS Code 4201.00.00  1 x 549070"])


def checked(case, goods, edition):
    s = case["s"]
    check = s.post(f"/api/v1/goods-lines/{goods['id']}/code-checks", {"edition_id": str(edition.id)})
    assert check.status_code == 201, check.content
    version = s.get(f"/api/v1/goods-lines/{goods['id']}").json()["row_version"]
    return {"goods_id": goods["id"], "code_check_id": check.json()["id"], "goods_line_version": version}


def bulk(case, items, reason="Codes de la facture conformes (essai fictif)."):
    return case["s"].post(
        f"/api/v1/revisions/{case['revision']}/code-confirmations", {"reason": reason, "items": items}
    )


# --- T77 : confirmation groupée, une décision attribuée par marchandise, tout ou rien ---------


def test_t77_bulk_confirmation_records_one_decision_per_goods_line(world, edition, session):
    case = make_case(session, edition)
    items = [
        checked(case, goods_with_code(case, amount="1000", code=code), edition) for code in ("4201.00.00", "9603.29.00")
    ]
    resp = bulk(case, items)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["confirmed"] == 2
    decisions = ClassificationDecision.objects.order_by("selected_code")
    assert [d.selected_code for d in decisions] == ["42010000", "96032900"]
    assert {d.reason for d in decisions} == {"Codes de la facture conformes (essai fictif)."}
    assert all(d.action == "confirm" and d.code_check_id for d in decisions)
    assert AuditEvent.objects.filter(event_type="goods_line.code_decided").count() == 2
    event = AuditEvent.objects.get(event_type="goods_line.codes_confirmed")
    assert event.current["count"] == 2 and event.current["codes"] == ["42010000", "96032900"]
    goods = {g["id"]: g for g in body["revision"]["goods_lines"]}
    assert all(goods[i["goods_id"]]["decision"]["is_current"] for i in items)


def test_t77_one_stale_line_cancels_the_whole_confirmation(world, edition, session):
    case = make_case(session, edition)
    first = checked(case, goods_with_code(case, amount="1000"), edition)
    second = checked(case, goods_with_code(case, amount="2000", code="9603.29.00"), edition)
    second["goods_line_version"] -= 1  # la ligne a changé depuis l'ouverture
    resp = bulk(case, [first, second])
    assert resp.status_code == 409, resp.content
    error = resp.json()
    assert error["details"]["goods_id"] == second["goods_id"] and "Aucun code n'a été confirmé" in error["message"]
    assert ClassificationDecision.objects.count() == 0
    assert not AuditEvent.objects.filter(event_type__in=["goods_line.code_decided", "goods_line.codes_confirmed"])


def test_t77_bulk_confirmation_refuses_incomplete_codes_reasonless_and_foreign_lines(world, edition, session):
    case = make_case(session, edition)
    ok = checked(case, goods_with_code(case, amount="1000"), edition)
    incomplete = checked(case, goods_with_code(case, amount="1000", code="9603"), edition)
    assert bulk(case, [ok, incomplete]).status_code == 422  # un code incomplet ne se confirme pas tel quel
    assert bulk(case, [ok], reason=" ").status_code == 400
    assert bulk(case, []).status_code == 400
    assert bulk(case, [ok, ok]).status_code == 400
    other_case = make_case(session, edition)
    assert bulk(other_case, [ok]).status_code == 404  # marchandise d'un autre dossier
    other = session("declarant@b.test")
    url = f"/api/v1/revisions/{case['revision']}/code-confirmations"
    assert other.post(url, {"reason": "x", "items": [ok]}).status_code == 404
    assert ClassificationDecision.objects.count() == 0


def test_t77_an_incomplete_code_is_completed_with_its_only_subdivision(world, edition, session):
    from apps.tariffs.models import TariffNode

    case = make_case(session, edition)
    ok = checked(case, goods_with_code(case, amount="1000"), edition)
    incomplete = checked(case, goods_with_code(case, amount="1000", code="4201"), edition)
    node = TariffNode.objects.get(edition=edition, code="42010000")
    wrong = TariffNode.objects.get(edition=edition, code="96032900")
    assert bulk(case, [ok, incomplete | {"node_id": str(wrong.id)}]).status_code == 422
    assert ClassificationDecision.objects.count() == 0
    resp = bulk(case, [ok, incomplete | {"node_id": str(node.id)}])
    assert resp.status_code == 201, resp.content
    assert sorted(ClassificationDecision.objects.values_list("action", flat=True)) == ["complete", "confirm"]


# --- T84 : archive complète du dossier ---------------------------------------------------------


def archive(case):
    resp = case["s"].post(f"/api/v1/cases/{case['id']}/archive")
    assert resp.status_code == 200, resp.content
    content = b"".join(resp.streaming_content)
    return resp, zipfile.ZipFile(io.BytesIO(content))


def test_t84_archive_gathers_pieces_exports_circuit_decisions_and_journal(world, schedule, edition, session):
    case, _ = ready_case(session, edition)
    file = SimpleUploadedFile("facture F-1.pdf", PIECE, content_type="application/pdf")
    resp = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "usage": "invoice"})
    assert resp.status_code == 201, resp.content
    detail = complete(case, world, edition)
    rev = act(case, "submit", detail["revision"]["row_version"]).json()["revision"]
    act(case, "validate", rev["row_version"], reason="Conforme (essai fictif)")

    resp, z = archive(case)
    assert resp["Content-Type"] == "application/zip" and "_dossier_complet.zip" in resp["Content-Disposition"]
    assert "_brouillon" not in resp["Content-Disposition"]
    names = set(z.namelist())
    assert z.read("revision-1/pieces/facture F-1.pdf") == PIECE  # octets d'origine, intacts
    ref = detail["reference"]
    assert {f"revision-1/exports/{ref}_r1.pdf", f"revision-1/exports/{ref}_r1.xlsx"} <= names
    assert z.read(f"revision-1/exports/{ref}_r1.pdf").startswith(b"%PDF")
    circuit = z.read("revision-1/circuit-validation.csv").decode("utf-8-sig")
    assert (
        "Soumis pour validation" in circuit and "Validé en interne" in circuit and "Conforme (essai fictif)" in circuit
    )
    decisions = z.read("revision-1/decisions-codes.csv").decode("utf-8-sig")
    assert "4201.00.00" in decisions and "Confirmer le code présent" in decisions
    frozen = json.loads(z.read("revision-1/calcul-valide.json"))
    assert frozen["fingerprint"] and frozen["snapshot"]["calculation"]
    journal = z.read("journal.csv").decode("utf-8-sig")
    assert "revision.validated" in journal and "revision.exported" in journal
    readme = z.read("LISEZMOI.txt").decode("utf-8")
    assert "validée en interne" in readme and "pas une acceptation par la Douane" in readme
    manifest = json.loads(z.read("manifeste.json"))
    assert manifest["internal_validation_only"] and manifest["altered"] == []
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f["path"])).hexdigest() == f["sha256"]
    assert next(f for f in manifest["files"] if f["source"] == "piece")["intact"] is True

    # Projet DAU et Excel générés une fois pour ce calcul, conservés et journalisés ; pas de doublon ensuite.
    assert CaseExport.objects.count() == 2
    archive(case)
    assert CaseExport.objects.count() == 2
    events = AuditEvent.objects.filter(event_type="case.archive_downloaded")
    assert events.count() == 2 and events.first().current["sha256"]


def test_t84_draft_archive_is_marked_and_bounded_to_the_company(world, schedule, edition, session):
    case, _ = ready_case(session, edition)
    complete(case, world, edition)
    resp, z = archive(case)
    assert "_dossier_complet_brouillon.zip" in resp["Content-Disposition"]
    assert "non validée en interne" in z.read("LISEZMOI.txt").decode("utf-8")
    assert "revision-1/calcul-valide.json" not in z.namelist()
    assert all(e.marking == "draft" for e in CaseExport.objects.all())
    assert session("declarant@b.test").post(f"/api/v1/cases/{case['id']}/archive").status_code == 404


def test_archive_names_never_escape_their_folder():
    assert _safe_name("../../etc/passwd", "x") == "passwd"
    assert _safe_name("C:\\temp\\..\\facture.pdf", "x") == "facture.pdf"
    assert _safe_name("..", "fallback") == "fallback"
    assert _safe_name("facture <F-1>.pdf", "x") == "facture _F-1_.pdf"
