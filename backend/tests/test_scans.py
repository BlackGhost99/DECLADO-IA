"""Numérisation des pièces : T39 à T45 (NUM-01 à NUM-08), T01 sur les lots numérisés.

Toutes les pages sont fictives (apps/scans/synthetic.py). Les tests OCR exigent Tesseract
(installé par le Dockerfile et la CI) ; sans lui, ils sont signalés comme sautés, jamais réussis.
"""

import io
import shutil

import pypdfium2 as pdfium
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.cases.models import CaseRevision
from apps.core import outbox
from apps.extraction.models import ExtractionRun
from apps.scans import synthetic
from apps.scans.models import ScanBatch, ScanPage
from apps.scans.segment import PageInfo, propose
from apps.scans.titles import PageReading, Word, read_page

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract absent de cette machine")
PDF = "application/pdf"


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def case(world, session):
    s = session("declarant@a.test")
    resp = s.post("/api/v1/cases", {"title": "Numérisation"})
    assert resp.status_code == 201, resp.content
    body = resp.json()
    return {"s": s, "id": body["id"], "revision": body["revision"]["id"]}


def new_batch(case, source="scanner"):
    resp = case["s"].post(f"/api/v1/cases/{case['id']}/scan-batches", {"source": source})
    assert resp.status_code == 201, resp.content
    return resp.json()


def send_files(case, batch, *files):
    payload = {"files": [SimpleUploadedFile(name, content, content_type=ctype) for name, content, ctype in files]}
    return case["s"].upload(f"/api/v1/scan-batches/{batch['id']}/files", payload)


def processed(case, batch):
    outbox.dispatch_pending()
    return case["s"].get(f"/api/v1/scan-batches/{batch['id']}").json()


def scanned(case, content, name="scan-arrivage.pdf", ctype=PDF):
    batch = new_batch(case)
    resp = send_files(case, batch, (name, content, ctype))
    assert resp.status_code == 201, resp.content
    return processed(case, batch)


def pages_of(batch, piece):
    numbers = {p["id"]: p["number"] for p in batch["pages"]}
    return [numbers[i] for i in piece["page_ids"]]


# --- Règles de reconnaissance et de découpage (NUM-04) -------------------------------------


def words(*lines):
    return [Word(text, top=0.05 + 0.04 * i, left=0.1) for i, line in enumerate(lines) for text in line.split()]


def test_title_is_read_at_the_top_with_its_number_and_page_marker():
    reading = read_page(words("CONNAISSEMENT MARITIME (BILL OF LADING)", "B/L N° FIC-2026-0456", "Page 1/2"))
    assert (reading.usage, reading.label, reading.reference, reading.marker) == (
        "transport",
        "Document de transport",
        "FIC-2026-0456",
        (1, 2),
    )
    # Un titre en bas de page (pied de page, mention) ne fait pas le type de la pièce.
    low = [Word("FACTURE", top=0.9)]
    assert read_page(low).usage == ""
    # « Référence facture » sur une liste de colisage : le premier titre lu l'emporte.
    assert read_page(words("LISTE DE COLISAGE", "Référence facture : FE-1")).usage == "packing_list"


def info(n, usage="", ref="", marker=None, blank=False):
    label = {"invoice": "Facture", "packing_list": "Liste de colisage"}.get(usage, "")
    return PageInfo(n, n, blank, PageReading(usage, label, label, ref, marker))


def test_segmentation_rules_are_explained_and_never_merge_two_numbers():
    proposal = propose(
        [
            info(1),  # aucun titre, aucune pièce en cours : non classée
            info(2, "invoice", "F-1", (1, 2)),
            info(3, "invoice", "F-1", (2, 2)),  # même facture : suite
            info(4, "invoice", "F-2"),  # autre numéro : nouvelle pièce
            info(5),  # sans titre : suite de la pièce en cours
            info(6, blank=True),  # page blanche : séparation, retirée
            info(7),  # après une séparation, sans titre : non classée
            info(8, marker=(1, 3)),  # « page 1/3 » sans titre : nouvelle pièce
            info(9, marker=(2, 3)),
        ]
    )
    assert [p.page_ids for p in proposal.pieces] == [[2, 3], [4, 5], [8, 9]]
    assert [p.usage for p in proposal.pieces] == ["invoice", "invoice", "other"]
    assert proposal.pieces[0].reason == "titre « Facture » reconnu en haut de la page 2, n° F-1"
    assert proposal.pieces[2].reason == "mention « page 1/3 » lue sur la page 8"
    assert proposal.unclassified == [1, 7] and proposal.blank == [6]


# --- T39 : lot du scanner découpé en pièces proposées (NUM-01, NUM-02, NUM-04) -------------


def test_scanner_batch_is_split_into_proposed_pieces(case):
    batch = scanned(case, synthetic.demo_batch())
    assert batch["state"] == "to_sort" and batch["job"]["state"] == "succeeded"
    assert batch["counts"] == {
        "pages": 6,
        "pending": 0,
        "kept": 5,
        "unclassified": 0,
        "blank_removed": 1,
        "hard_to_read": 0,
        "pieces": 3,
    }
    invoice, transport, packing = batch["pieces"]
    assert (invoice["usage"], pages_of(batch, invoice)) == ("invoice", [1, 2])
    assert invoice["reason"] == "titre « Facture » reconnu en haut de la page 1, n° FE-2026-0417"
    assert (transport["usage"], pages_of(batch, transport)) == ("transport", [4])
    assert (packing["usage"], pages_of(batch, packing)) == ("packing_list", [5, 6])
    blank = batch["pages"][2]
    assert blank["blank"] and blank["removed"] == "blank" and blank["removed_label"] == "Page blanche retirée"
    assert {p["text_origin"] for p in batch["pages"] if not p["blank"]} == {"pdf_text"}
    # L'original déposé est conservé ; rien n'est encore rattaché au dossier.
    assert batch["sources"][0]["name"] == "scan-arrivage.pdf" and batch["sources"][0]["page_count"] == 6
    assert case["s"].get(f"/api/v1/cases/{case['id']}/documents").json()["results"] == []
    image = case["s"].get(f"/api/v1/scan-pages/{batch['pages'][0]['id']}/image", size="thumb")
    assert image.status_code == 200 and image["Content-Type"] == "image/jpeg"
    assert AuditEvent.objects.filter(event_type="scan.sorting_proposed").count() == 1


def test_several_files_and_tiff_pages_follow_the_order_of_deposit(case):
    first = synthetic.text_pdf([synthetic.page("FACTURE N° A-1", "ligne")])
    second = synthetic.tiff(synthetic.text_pdf([synthetic.page("", "Annexe"), synthetic.page("", "Annexe 2")]))
    batch = new_batch(case)
    resp = send_files(case, batch, ("a.pdf", first, PDF), ("b.tif", second, "image/tiff"))
    assert resp.status_code == 201, resp.content
    batch = processed(case, batch)
    assert [(p["source_name"], p["source_page"]) for p in batch["pages"]] == [("a.pdf", 1), ("b.tif", 1), ("b.tif", 2)]
    # Le TIFF n'a pas de couche texte : sans OCR lisible, ses pages suivent la facture en cours.
    [piece] = batch["pieces"]
    assert pages_of(batch, piece) == [1, 2, 3]


def test_tiff_is_refused_as_a_direct_case_document(case):
    content = synthetic.tiff(synthetic.text_pdf([synthetic.page("FACTURE")]))
    file = SimpleUploadedFile("scan.tif", content, content_type="image/tiff")
    resp = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "usage": "invoice"})
    assert resp.status_code == 422 and "lot numérisé" in resp.json()["message"]


def test_batch_page_limit_is_explicit(case, settings):
    settings.SCAN_BATCH_MAX_PAGES = 4
    batch = new_batch(case)
    resp = send_files(case, batch, ("lot.pdf", synthetic.demo_batch(), PDF))
    assert resp.status_code == 413 and resp.json()["code"] == "BATCH_TOO_LARGE"
    assert ScanPage.objects.count() == 0


# --- T40 : tri par l'agent (NUM-05) ---------------------------------------------------------


def test_agent_can_cut_join_move_rotate_remove_and_retype(case):
    batch = scanned(case, synthetic.demo_batch())
    s = case["s"]
    invoice, transport, packing = batch["pieces"]
    second_invoice_page = invoice["page_ids"][1]

    batch = s.post(f"/api/v1/scan-pages/{second_invoice_page}/split").json()
    assert [pages_of(batch, p) for p in batch["pieces"]] == [[1], [4], [5, 6], [2]]
    cut = batch["pieces"][3]
    assert cut["usage"] == "invoice" and cut["usage_by_user"]

    batch = s.post(f"/api/v1/scan-pieces/{cut['id']}/join-previous").json()
    assert [pages_of(batch, p) for p in batch["pieces"]] == [[1, 2], [4], [5, 6]]

    annex = packing["page_ids"][1]
    batch = s.patch(f"/api/v1/scan-pages/{annex}", {"piece_id": "new", "usage": "other"}).json()
    assert [pages_of(batch, p) for p in batch["pieces"]][-1] == [6]
    batch = s.patch(f"/api/v1/scan-pages/{annex}", {"piece_id": None}).json()
    assert batch["counts"]["unclassified"] == 1 and len(batch["pieces"]) == 3  # la pièce vide disparaît

    batch = s.patch(f"/api/v1/scan-pages/{annex}", {"rotation": 90, "removed": True}).json()
    page = next(p for p in batch["pages"] if p["id"] == annex)
    assert page["rotation"] == 90 and page["removed"] == "user" and batch["counts"]["unclassified"] == 0
    assert s.patch(f"/api/v1/scan-pages/{annex}", {"rotation": 45}).status_code == 400

    batch = s.patch(f"/api/v1/scan-pieces/{transport['id']}", {"usage": "origin"}).json()
    retyped = next(p for p in batch["pieces"] if p["id"] == transport["id"])
    assert retyped["usage"] == "origin" and retyped["reason"] == "type choisi par l'agent"
    types = set(AuditEvent.objects.filter(event_type__startswith="scan.").values_list("event_type", flat=True))
    assert {"scan.piece_split", "scan.piece_joined", "scan.page_updated", "scan.piece_type_set"} <= types


def test_a_page_can_be_taken_again_and_keeps_its_place(case):
    batch = scanned(case, synthetic.demo_batch())
    old = batch["pages"][0]
    retake = synthetic.text_pdf([synthetic.page("FACTURE N° FE-2026-0417", "Reprise nette", "Page 1/2")])
    file = SimpleUploadedFile("reprise.pdf", retake, content_type=PDF)
    resp = case["s"].upload(f"/api/v1/scan-pages/{old['id']}/replace", {"file": file})
    assert resp.status_code == 201, resp.content
    batch = processed(case, case and resp.json())
    first = batch["pages"][0]
    assert first["id"] != old["id"] and first["number"] == 1 and first["source_name"] == "reprise.pdf"
    assert first["replaces_id"] == old["id"] and first["piece_id"] == old["piece_id"]
    assert ScanPage.objects.get(pk=old["id"]).removed == "replaced"


# --- T41 : rattachement au dossier (NUM-06) --------------------------------------------------


def test_attach_creates_one_pdf_per_piece_and_starts_reading_the_invoices(case):
    batch = scanned(case, synthetic.demo_batch())
    s = case["s"]
    resp = s.post(f"/api/v1/scan-batches/{batch['id']}/attach")
    assert resp.status_code == 200, resp.content
    batch = resp.json()
    assert batch["state"] == "attached"
    docs = s.get(f"/api/v1/cases/{case['id']}/documents").json()["results"]
    assert [(d["usage"], d["document"]["original_name"]) for d in docs] == [
        ("invoice", f"{_reference(case)} Facture.pdf"),
        ("transport", f"{_reference(case)} Document de transport.pdf"),
        ("packing_list", f"{_reference(case)} Liste de colisage.pdf"),
    ]
    assert [p["case_document"]["id"] for p in batch["pieces"]] == [d["id"] for d in docs]
    stored = s.get(f"/api/v1/documents/{docs[0]['document']['id']}/download").json()["url"]
    pdf = pdfium.PdfDocument(b"".join(s.client.get(stored).streaming_content))
    assert len(pdf) == 2
    pdf.close()
    [run] = ExtractionRun.objects.all()
    assert str(run.case_document_id) == docs[0]["id"] and run.options == {"ocr": True}
    # Un lot rattaché n'est plus modifiable.
    page = batch["pages"][0]["id"]
    assert s.patch(f"/api/v1/scan-pages/{page}", {"rotation": 90}).json()["code"] == "BATCH_CLOSED"
    assert s.post(f"/api/v1/scan-batches/{batch['id']}/attach").status_code == 409


def _reference(case):
    return case["s"].get(f"/api/v1/cases/{case['id']}").json()["reference"]


def test_unclassified_pages_stay_in_the_batch_and_empty_batch_cannot_attach(case):
    content = synthetic.text_pdf([synthetic.page("", "Sans titre"), synthetic.page("FACTURE N° Z-9", "ligne")])
    batch = scanned(case, content)
    assert batch["counts"]["unclassified"] == 1 and len(batch["pieces"]) == 1
    batch = case["s"].post(f"/api/v1/scan-batches/{batch['id']}/attach").json()
    assert batch["state"] == "attached" and batch["counts"]["unclassified"] == 1
    other = scanned(case, synthetic.text_pdf([synthetic.page("", "Rien de reconnu")]))
    resp = case["s"].post(f"/api/v1/scan-batches/{other['id']}/attach")
    assert resp.status_code == 409 and resp.json()["code"] == "NOTHING_TO_ATTACH"


def test_batch_refused_on_validated_revision(case):
    batch = new_batch(case)
    CaseRevision.objects.filter(pk=case["revision"]).update(state="validated")
    resp = send_files(case, batch, ("lot.pdf", synthetic.demo_batch(), PDF))
    assert resp.status_code == 409 and resp.json()["code"] == "REVISION_NOT_EDITABLE"


# --- T42 : prise de vue au téléphone (NUM-03) -------------------------------------------------


def test_photos_form_the_pieces_chosen_while_shooting(case):
    s = case["s"]
    batch = new_batch(case, "camera")
    invoice = synthetic.text_pdf([synthetic.page("FACTURE N° P-1", "ligne")])
    photo = synthetic.photo(invoice)

    def shoot(**extra):
        file = SimpleUploadedFile("photo.jpg", photo, content_type="image/jpeg")
        resp = s.upload(f"/api/v1/scan-batches/{batch['id']}/photos", {"file": file, **extra})
        assert resp.status_code == 201, resp.content
        return resp.json()["batch"]

    state = shoot(usage="invoice")
    piece = state["pieces"][0]
    assert (piece["usage"], piece["reason"]) == ("invoice", "choisi à la prise de vue")
    state = shoot(piece_id=piece["id"])
    state = shoot(usage="transport")
    assert state["state"] == "open"
    outbox.dispatch_pending()
    state = s.post(f"/api/v1/scan-batches/{batch['id']}/finish").json()
    assert state["state"] == "to_sort"
    assert [(p["usage"], len(p["page_ids"])) for p in state["pieces"]] == [("invoice", 2), ("transport", 1)]
    first = state["pages"][0]
    assert "Photo recadrée sur la feuille." in first["notes"]
    page = ScanPage.objects.get(pk=first["id"])
    assert page.width < 1.2 * 595 * 120 / 72  # le fond sombre a été retiré


# --- T43 : pages scannées lues par OCR (NUM-04, NUM-07) --------------------------------------


@needs_tesseract
def test_scanned_pages_are_read_by_ocr_and_an_upside_down_page_is_turned(case):
    content = synthetic.text_pdf(
        [
            synthetic.page("FACTURE N° FE-2026-0417", "Fournisseur : Fictive Energie GmbH", "Total 3 000,00 EUR"),
            synthetic.page("CERTIFICAT D'ORIGINE", "N° CO-FIC-2026-0009", "Pays d'origine : Allemagne"),
        ],
        size=16,
    )
    batch = scanned(case, synthetic.scanned_pdf(content, dpi=200, rotate={2: 180}))
    assert {p["text_origin"] for p in batch["pages"]} == {"ocr"}
    assert [p["usage"] for p in batch["pieces"]] == ["invoice", "origin"]
    turned = batch["pages"][1]
    assert "Page remise à l'endroit." in turned["notes"]
    assert batch["pieces"][1]["reason"].startswith("titre « Certificat d'origine » reconnu")


def test_without_ocr_pages_are_flagged_and_nothing_is_invented(case, monkeypatch):
    import pytesseract

    def missing(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_languages", missing)
    content = synthetic.scanned_pdf(synthetic.text_pdf([synthetic.page("FACTURE N° X-1", "ligne")]))
    batch = scanned(case, content)
    [page] = batch["pages"]
    assert page["state"] == "failed" and page["hard_to_read"] and page["title"] == ""
    assert any("OCR" in note for note in page["notes"])
    assert batch["pieces"] == [] and batch["counts"]["unclassified"] == 1


# --- T01 : isolation et rôles ----------------------------------------------------------------


def test_other_company_cannot_see_or_change_a_batch(case, session):
    batch = scanned(case, synthetic.demo_batch())
    page, piece = batch["pages"][0]["id"], batch["pieces"][0]["id"]
    b = session("declarant@b.test")
    assert b.get(f"/api/v1/cases/{case['id']}/scan-batches").status_code == 404
    assert b.post(f"/api/v1/cases/{case['id']}/scan-batches", {"source": "scanner"}).status_code == 404
    assert b.get(f"/api/v1/scan-batches/{batch['id']}").status_code == 404
    files = {"files": [SimpleUploadedFile("x.pdf", synthetic.demo_batch(), content_type=PDF)]}
    assert b.upload(f"/api/v1/scan-batches/{batch['id']}/files", files).status_code == 404
    photo = {"file": SimpleUploadedFile("p.jpg", b"\xff\xd8\xff", content_type="image/jpeg")}
    assert b.upload(f"/api/v1/scan-batches/{batch['id']}/photos", photo).status_code == 404
    for action in ("finish", "attach", "cancel"):
        assert b.post(f"/api/v1/scan-batches/{batch['id']}/{action}").status_code == 404
    assert b.patch(f"/api/v1/scan-pages/{page}", {"rotation": 90}).status_code == 404
    assert b.post(f"/api/v1/scan-pages/{page}/split").status_code == 404
    assert b.upload(f"/api/v1/scan-pages/{page}/replace", photo).status_code == 404
    assert b.get(f"/api/v1/scan-pages/{page}/image").status_code == 404
    assert b.patch(f"/api/v1/scan-pieces/{piece}", {"usage": "other"}).status_code == 404
    assert b.post(f"/api/v1/scan-pieces/{piece}/join-previous").status_code == 404
    assert ScanBatch.objects.get(pk=batch["id"]).state == "to_sort"


def test_admin_without_preparation_role_reads_but_cannot_scan(case, session):
    batch = scanned(case, synthetic.demo_batch())
    admin = session("admin@a.test")
    assert admin.get(f"/api/v1/scan-batches/{batch['id']}").status_code == 200
    assert admin.post(f"/api/v1/cases/{case['id']}/scan-batches", {"source": "scanner"}).status_code == 403
    assert admin.post(f"/api/v1/scan-batches/{batch['id']}/attach").status_code == 403


def test_page_image_is_a_real_jpeg_and_rotation_is_applied(case):
    from PIL import Image

    batch = scanned(case, synthetic.demo_batch())
    page = batch["pages"][0]
    case["s"].patch(f"/api/v1/scan-pages/{page['id']}", {"rotation": 90})
    body = case["s"].get(f"/api/v1/scan-pages/{page['id']}/image").content
    image = Image.open(io.BytesIO(body))
    assert image.format == "JPEG" and image.width > image.height  # page portrait tournée d'un quart
