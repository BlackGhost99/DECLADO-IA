"""Dépôt groupé : DEP-01 à DEP-06 (T83), sur les 9 pièces fictives de trois importateurs.

Trois envois (BatiPro, EquaTech, Textilia), chacun avec facture commerciale, connaissement et
facture d'assurance. Les pièces se citent entre elles (n° de facture, n° de B/L, conteneur) :
elles doivent former trois dossiers proposés, sans rien créer avant la confirmation.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.cases.models import CaseDocument, CustomsCase
from apps.extraction.models import ExtractionRun

PIECES = Path(settings.BASE_DIR).parent / "fixtures" / "synthetic" / "depot-groupe"


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def deposit(s, name):
    file = SimpleUploadedFile(name, (PIECES / name).read_bytes(), content_type="application/pdf")
    resp = s.upload("/api/v1/intake/documents", {"file": file})
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_t83_mixed_pieces_are_split_into_one_proposed_case_per_shipment(world, session):
    s = session("declarant@a.test")
    names = sorted(p.name for p in PIECES.glob("*.pdf"))
    assert len(names) == 9
    read = [deposit(s, n) for n in names]
    by_name = {r["name"]: r for r in read}
    bl = by_name["02_connaissement_maritime_batipro.pdf"]
    assert bl["type"] == "bill_of_lading" and bl["party"] == "BatiPro Gabon SARL"
    assert {"kind": "invoice", "value": "IIC-2026-7784", "role": "cited"} in bl["references"]
    assert CustomsCase.objects.count() == 0  # rien n'est créé au dépôt

    ids = [r["document_id"] for r in read]
    proposal = s.post("/api/v1/intake/proposal", {"document_ids": ids}).json()
    assert proposal["unassigned"] == []
    groups = {g["party"]: g for g in proposal["groups"]}
    assert set(groups) == {"BatiPro Gabon SARL", "EquaTech Distribution SARL", "Textilia Services Gabon SA"}
    for party, group in groups.items():
        assert len(group["documents"]) == 3 and group["warnings"] == []
        assert {d["party"] for d in group["documents"]} == {party}
        assert {r["kind"] for r in group["reasons"]} == {"invoice", "bl", "container"}
    assert CustomsCase.objects.count() == 0  # la proposition ne crée rien non plus

    # L'agent confirme ; il peut déplacer une pièce, ici il garde la proposition.
    body = [{"title": g["title"], "document_ids": [d["document_id"] for d in g["documents"]]} for g in groups.values()]
    resp = s.post("/api/v1/intake/cases", {"groups": body})
    assert resp.status_code == 201, resp.content
    created = resp.json()["results"]
    assert len(created) == 3 and all(c["documents"] == 3 for c in created)
    batipro = CustomsCase.objects.get(title="BatiPro Gabon SARL")
    links = CaseDocument.objects.filter(revision=batipro.current_revision)
    assert sorted(lk.usage for lk in links) == ["insurance", "invoice", "transport"]
    assert ExtractionRun.objects.filter(case_document__in=links).count() == 3  # lecture complète demandée
    assert AuditEvent.objects.filter(event_type="case.created_from_intake").count() == 3

    # Le même fichier déposé à nouveau est reconnu, pas doublé.
    again = deposit(s, "01_facture_commerciale_batipro.pdf")
    assert again["document_id"] == by_name["01_facture_commerciale_batipro.pdf"]["document_id"]
    assert again["already_in"] == [batipro.reference]


def test_t83_a_piece_without_reference_stays_to_be_sorted_and_names_never_merge(world, session):
    s = session("declarant@a.test")
    invoice = deposit(s, "01_facture_commerciale_textilia.pdf")
    other = s.upload(
        "/api/v1/intake/documents",
        {"file": SimpleUploadedFile("note.pdf", _blank_pdf(), content_type="application/pdf")},
    ).json()
    proposal = s.post("/api/v1/intake/proposal", {"document_ids": [invoice["document_id"], other["document_id"]]})
    body = proposal.json()
    assert [g["party"] for g in body["groups"]] == ["Textilia Services Gabon SA"]
    assert [u["document_id"] for u in body["unassigned"]] == [other["document_id"]]


def test_t83_intake_is_bounded_to_the_company(world, session):
    s = session("declarant@a.test")
    doc = deposit(s, "01_facture_commerciale_equatech.pdf")
    other = session("declarant@b.test")
    ids = [doc["document_id"]]
    assert other.post("/api/v1/intake/proposal", {"document_ids": ids}).status_code == 404
    groups = [{"title": "x", "document_ids": ids}]
    assert other.post("/api/v1/intake/cases", {"groups": groups}).status_code == 404
    assert s.post("/api/v1/intake/cases", {"groups": [{"title": "x", "document_ids": ids * 2}]}).status_code == 400
    assert CustomsCase.objects.count() == 0


def _blank_pdf() -> bytes:
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(100, 750, "Note interne sans reference")
    c.save()
    return buffer.getvalue()


def test_progec_is_read_as_a_supporting_document(world, session):
    s = session("declarant@a.test")
    invoice = deposit(s, "01_facture_commerciale_batipro.pdf")
    permit = _drop_pdf(
        s,
        "6_PROGEC_AUTORISATIONS.pdf",
        [
            "PROGEC - AUTORISATION D'IMPORTATION",
            "Importateur: BatiPro Gabon SARL",
            "Facture liee: IIC-2026-7784",
        ],
    )
    assert permit["type"] == "sectoral_permit"
    assert permit["type_source"] == "title"
    assert permit["reading_status"] == "native"
    ids = [invoice["document_id"], permit["document_id"]]
    result = s.post("/api/v1/intake/proposal", {"document_ids": ids}).json()
    assert [len(group["documents"]) for group in result["groups"]] == [2]
    assert result["groups"][0]["confidence"] == "high"
    created = s.post("/api/v1/intake/cases", {"groups": [{"title": "PROGEC", "document_ids": ids}]})
    assert created.status_code == 201
    link = CaseDocument.objects.get(document_id=permit["document_id"])
    assert link.detected_type == "sectoral_permit"
    assert link.usage == "other"
    assert ExtractionRun.objects.get(case_document=link).options["reader"] == "permit"


def test_text_without_document_type_is_read(world, session):
    piece = _drop_pdf(session("declarant@a.test"), "note.pdf", ["Une note interne sans document douanier."])
    assert piece["reading_status"] == "native"
    assert piece["read"] is True
    assert not piece["type"]


def test_progec_filename_does_not_turn_empty_ocr_into_a_read_document(world, session, monkeypatch):
    from apps.extraction.adapters.ocr import OcrResult

    monkeypatch.setattr("apps.extraction.adapters.ocr.ocr_pdf_page", lambda *args, **kwargs: OcrResult(None))
    piece = _drop_pdf(session("declarant@a.test"), "6_PROGEC_AUTORISATIONS.pdf", [])
    assert piece["type"] == "sectoral_permit"
    assert piece["type_source"] == "filename"
    assert piece["reading_status"] == "no_text"
    assert piece["read"] is False
    assert piece["references"] == []


def _drop_pdf(session, name, lines):
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        pdf.drawString(75, 790 - 25 * index, line)
    pdf.showPage()
    pdf.save()
    upload = SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")
    response = session.upload("/api/v1/intake/documents", {"file": upload})
    assert response.status_code == 201, response.content
    return response.json()
