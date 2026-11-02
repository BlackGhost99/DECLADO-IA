"""Liste de colisage et certificat d'origine (T87) : lus, rattachés au dépôt groupé par le n° de
facture qu'ils citent, et masse nette reprise au DAU. Pièces fictives (apps/extraction/synthetic.py).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.cases.dau import data
from apps.cases.models import CaseDocument, CustomsCase, Invoice
from apps.extraction import synthetic
from apps.extraction.models import ExtractionRun
from tests.test_depot_groupe import deposit
from tests.test_extraction import make_edition
from tests.test_lecture_pieces import BL, read_piece, upload
from tests.test_validation import complete, ready_case


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def drop(s, name, content):
    resp = s.upload(
        "/api/v1/intake/documents", {"file": SimpleUploadedFile(name, content, content_type="application/pdf")}
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_t87_packing_list_and_origin_certificate_join_their_shipment_by_invoice_number(world, session):
    s = session("declarant@a.test")
    invoice = deposit(s, "01_facture_commerciale_batipro.pdf")
    other = deposit(s, "01_facture_commerciale_textilia.pdf")
    packing = drop(s, "colisage.pdf", synthetic.packing_list_pdf())
    origin = drop(s, "origine.pdf", synthetic.origin_certificate_pdf())
    assert packing["type"] == "packing_list" and origin["type"] == "certificate_of_origin"
    assert {"kind": "invoice", "value": "IIC-2026-7784", "role": "cited"} in packing["references"]
    assert origin["party"] == "BatiPro Gabon SARL"
    ids = [d["document_id"] for d in (invoice, other, packing, origin)]
    proposal = s.post("/api/v1/intake/proposal", {"document_ids": ids}).json()
    assert proposal["unassigned"] == []
    groups = {frozenset(d["name"] for d in g["documents"]) for g in proposal["groups"]}
    assert frozenset({"01_facture_commerciale_batipro.pdf", "colisage.pdf", "origine.pdf"}) in groups
    assert frozenset({"01_facture_commerciale_textilia.pdf"}) in groups
    batipro = next(g for g in proposal["groups"] if len(g["documents"]) == 3)
    body = [{"title": "BatiPro", "document_ids": [d["document_id"] for d in batipro["documents"]]}]
    assert s.post("/api/v1/intake/cases", {"groups": body}).status_code == 201
    case = CustomsCase.objects.get(title="BatiPro")
    links = CaseDocument.objects.filter(revision=case.current_revision)
    assert sorted(lk.usage for lk in links) == ["invoice", "origin", "packing_list"]
    readers_ = set(ExtractionRun.objects.filter(case_document__in=links).values_list("options__reader", flat=True))
    assert readers_ == {"invoice", "packing", "origin"}
    assert (
        Invoice.objects.filter(revision=case.current_revision).count() <= 1
    )  # ni colisage ni certificat ne font une facture


def test_t87_packing_list_net_weight_fills_the_dau(world, session):
    call_command("seed_document_types")
    edition = make_edition()
    case, _ = ready_case(session, edition)
    complete(case, world, edition)
    read_piece(case, upload(case, BL, usage="auto"))
    file = SimpleUploadedFile("colisage.pdf", synthetic.packing_list_pdf(), content_type="application/pdf")
    link = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "usage": "auto"}).json()
    assert link["usage"] == "packing_list"
    run = read_piece(case, link)
    assert run.options["reader"] == "packing" and run.status == "succeeded"
    measures = case["s"].get(f"/api/v1/cases/{case['id']}").json()["revision"]["measures"]
    assert measures["net_weight_kg"] == "3610" and measures["gross_weight_kg"] == "3940"
    c = CustomsCase.objects.get(pk=case["id"])
    d = data(c, c.current_revision, {"articles": []})
    assert d["net_weight"] == "3 610" and d["goods"][0]["net"] == "3 610"
