"""Lecture des pièces d'un dossier : LEC-01 à LEC-10 (T51 à T57).

Jeu BatiPro fictif (fixtures/synthetic/batipro) : facture commerciale, connaissement et facture
d'assurance d'un même envoi, informations rangées en grilles « libellé | valeur ».
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.cases.models import CaseDocument, CaseRevision, Invoice
from apps.core import outbox
from apps.document_graph import intelligence
from apps.document_graph.models import DocumentInvoiceLink, Shipment
from apps.extraction import layout
from apps.extraction.adapters.pdf_words import page_words
from apps.extraction.adapters.words import rows_from_words
from apps.extraction.models import ExtractionRun
from apps.extraction.readers import detect_type, read
from apps.regulations.models import CompanyDocumentPolicy, DocumentClassification, DocumentType
from apps.regulations.taxonomy import TYPES
from tests.test_extraction import make_case, make_edition

BATIPRO = Path(settings.BASE_DIR).parent / "fixtures" / "synthetic" / "batipro"
INVOICE, BL, INSURANCE = "01_facture_commerciale.pdf", "02_connaissement.pdf", "03_facture_assurance.pdf"
# Les mêmes pièces fournies par l'utilisateur, avec un filigrane « DOCUMENT FICTIF - TEST » en biais.
WATERMARKED = (
    "01_facture_commerciale_filigrane.pdf",
    "02_connaissement_filigrane.pdf",
    "03_facture_assurance_filigrane.pdf",
)
SETS = [(INVOICE, BL, INSURANCE), WATERMARKED]


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def pages(name):
    with pdfplumber.open(BATIPRO / name) as pdf:
        return [
            rows_from_words(page_words(page), page_number=n, width=float(page.width), height=float(page.height))
            for n, page in enumerate(pdf.pages, start=1)
        ]


def values(doc):
    return {name: value.parsed for name, value in doc.header.items()}


@pytest.mark.parametrize("name", [INVOICE, "01_facture_commerciale_navigateur.pdf", WATERMARKED[0]])
def test_t51_invoice_grid_letterhead_freight_and_total_are_read(name):
    """LEC-01 à LEC-06 : grille de libellés, raison sociale en tête, « Ocean freight », total imprimé."""
    doc = read(pages(name))
    got = values(doc)
    assert got["invoice_number"] == "IIC-2026-7784"
    assert got["currency"] == "EUR"
    assert got["incoterm"] == "CFR Owendo"
    assert got["buyer_name"] == "BatiPro Gabon SARL"
    assert got["supplier_name"] == "Iberica Industrial Components S.L."
    assert doc.header["supplier_name"].origin == "inferred"  # place en tête : à vérifier
    assert got["declared_total"] == Decimal("18554.00")
    assert got["related_bl"] == "MEDAF-BCN-OWD-2610052"
    # 03/10/2026 sur une facture en anglais : jour/mois déduit de l'adresse en Espagne, marqué déduit.
    assert got["invoice_date"] == date(2026, 10, 3)
    assert doc.header["invoice_date"].origin == "inferred"
    assert "Espana" in doc.header["invoice_date"].notes[0]
    codes = [line.codes[0].raw for line in doc.lines]
    assert codes == ["8481.80", "7307.19", "8413.70"]
    assert [line.fields["amount"].parsed for line in doc.lines] == [
        Decimal("5860.00"),
        Decimal("3184.00"),
        Decimal("7080.00"),
    ]
    charges = {c.kind: c.amount.parsed for c in doc.charges}
    assert charges == {"subtotal": Decimal("16124.00"), "fee": Decimal("2430.00"), "total": Decimal("18554.00")}


def test_t52_ambiguous_date_is_never_guessed_without_an_explicit_country():
    """LEC-06 : sans pays d'usage jour/mois dans l'adresse de l'émetteur, la date reste ambiguë."""
    parsed = read(pages(INVOICE))
    header = {"invoice_date": layout.Value("03/10/2026", None, layout.Status.AMBIGUOUS, notes=["?"])}
    reader = layout._Reader(None, True, "read")
    layout._resolve_day_month(header, [], reader)
    assert header["invoice_date"].parsed is None and header["invoice_date"].status == "ambiguous"
    assert "US" in layout.MONTH_FIRST_OR_MIXED and parsed.header["invoice_date"].parsed is not None


@pytest.mark.parametrize(
    ("text", "is_fee"),
    [
        ("Ocean freight 2 430.00", True),
        ("Frais de port 50,00", True),
        ("Port 30,00", True),
        ("Port de déchargement : Owendo", False),
        ("Port of discharge Owendo", False),
    ],
)
def test_t52_fee_rows(text, is_fee):
    """LEC-04 : un lieu (« Port de déchargement ») n'est pas un frais."""
    assert bool(layout._FEE.match(layout.norm(text))) is is_fee


def test_t51_watermark_letters_do_not_break_the_reading():
    """LEC-03 : les lettres d'un filigrane en biais tombent dans le texte (« SubtRotal ») ; elles sont retirées."""
    with pdfplumber.open(BATIPRO / WATERMARKED[0]) as pdf:
        raw = " ".join(w["text"] for w in pdf.pages[0].extract_words(x_tolerance=2))
        clean = " ".join(w["text"] for w in page_words(pdf.pages[0]))
    assert "SubtRotal" in raw and "OcAean" in raw
    assert "Subtotal" in clean and "Ocean freight" in clean and "FICTIF" not in clean


@pytest.mark.parametrize(("invoice", "bl", "insurance"), SETS)
def test_t53_title_gives_the_piece_type(invoice, bl, insurance):
    """LEC-07 : le type vient du titre de la première page, y compris un titre sur deux lignes."""
    assert detect_type(pages(invoice))["code"] == "commercial_invoice"
    assert detect_type(pages(bl))["code"] == "bill_of_lading"
    found = detect_type(pages(insurance))
    assert found["code"] == "insurance_invoice" and found["excerpt"] == "FACTURE D ASSURANCE"
    assert detect_type([]) is None


@pytest.mark.parametrize(("bl_name", "insurance_name"), [(s[1], s[2]) for s in SETS])
def test_t54_bill_of_lading_and_insurance_fields_are_read(bl_name, insurance_name):
    """LEC-08, LEC-09 : informations utiles d'un B/L et d'une facture d'assurance, sans facture créée.
    Le libellé « MEASUREMEN » coupé sur deux lignes (« T » dessous) reste un libellé."""
    bl = values(read(pages(bl_name), "transport"))
    assert bl["transport_number"] == "MEDAF-BCN-OWD-2610052"
    assert bl["issue_date"] == date(2026, 10, 5)
    assert bl["shipper"] == "Iberica Industrial Components S.L."
    assert bl["consignee"] == "BatiPro Gabon SARL"
    assert bl["vessel"] == "MV Santa Elena"
    assert bl["port_of_discharge"] == "Owendo, Gabon"
    assert bl["related_invoice"] == "IIC-2026-7784"
    assert bl["container"] == "MSCU 771205-4"
    assert bl["packages"] == "9 caisses bois" and bl["gross_weight"] == "3 940 kg"
    assert bl["measurement"] == "13.10 m3"
    insurance = values(read(pages(insurance_name), "insurance"))
    assert insurance["issuer"] == "Assurances du Littoral Gabon SA"
    assert insurance["document_number"] == "ALG-2026-FA-8841"
    assert insurance["issue_date"] == date(2026, 10, 7)
    assert insurance["policy_number"] == "ALG-CARGO-26-44102"
    assert insurance["insured"] == "BatiPro Gabon SARL"
    assert insurance["related_bl"] == "MEDAF-BCN-OWD-2610052"
    assert insurance["related_invoice"] == "IIC-2026-7784"
    assert insurance["insured_value"] == Decimal("20500.00")
    assert insurance["premium_total"] == Decimal("111.93")


def upload(case, name, **data):
    file = SimpleUploadedFile(name, (BATIPRO / name).read_bytes(), content_type="application/pdf")
    resp = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, **data})
    assert resp.status_code == 201, resp.content
    return resp.json()


def read_piece(case, link):
    resp = case["s"].post(f"/api/v1/case-documents/{link['id']}/extractions", {})
    assert resp.status_code == 202, resp.content
    assert outbox.dispatch_pending() >= 1
    return ExtractionRun.objects.get(pk=resp.json()["id"])


@pytest.fixture
def batipro(world, session):
    call_command("seed_document_types")
    case = make_case(session, make_edition())
    links = {name: upload(case, name, usage="auto") for name in (INVOICE, BL, INSURANCE)}
    return case, links


def test_t55_auto_upload_detects_type_and_reads_each_piece_its_way(batipro):
    """LEC-07 à LEC-09 : dépôt « auto », lecture selon le type ; l'assurance ne crée aucune facture."""
    case, links = batipro
    assert {n: (lk["usage"], lk["document_type"]["code"]) for n, lk in links.items()} == {
        INVOICE: ("invoice", "commercial_invoice"),
        BL: ("transport", "bill_of_lading"),
        INSURANCE: ("insurance", "insurance_invoice"),
    }
    assert links[INSURANCE]["document_type"]["source"] == "detected"
    assert links[INSURANCE]["document_type"]["evidence"]["excerpt"] == "FACTURE D ASSURANCE"
    runs = {name: read_piece(case, link) for name, link in links.items()}
    assert {name: run.options["reader"] for name, run in runs.items()} == {
        INVOICE: "invoice",
        BL: "transport",
        INSURANCE: "insurance",
    }
    [invoice] = Invoice.objects.all()  # la facture d'assurance n'est pas une facture commerciale
    assert invoice.invoice_number == "IIC-2026-7784" and invoice.buyer_name == "BatiPro Gabon SARL"
    assert invoice.lines.count() == 3 and invoice.declared_total == Decimal("18554.00")
    docs = case["s"].get(f"/api/v1/cases/{case['id']}/documents").json()["results"]
    summary = next(d for d in docs if d["id"] == links[INSURANCE]["id"])["latest_extraction"]
    fields = {f["field"]: f for f in summary["fields"]}
    assert summary["reader"] == "insurance" and summary["invoice_id"] is None
    assert fields["premium_total"]["parsed"] == "111.93" and fields["premium_total"]["span"]["page"] == 1
    assert fields["insured"]["raw"] == "BatiPro Gabon SARL"


def test_t56_checklist_and_matching_use_the_detected_types(batipro):
    """LEC-07, LEC-10 : pièces demandées par la société cochées « reçues, à vérifier » ; références
    croisées proposées au rapprochement, jamais acceptées d'office."""
    case, links = batipro
    for link in links.values():
        read_piece(case, link)
    org = CaseDocument.objects.get(pk=links[INVOICE]["id"]).organization
    for code in ("commercial_invoice", "insurance_invoice", "bill_of_lading"):
        CompanyDocumentPolicy.objects.create(
            organization=org, document_type=DocumentType.objects.get(code=code), reason="Demandé au client"
        )
    CaseRevision.objects.filter(pk=case["revision"]).update(regime="IM4", planned_declaration_date=date(2026, 10, 20))
    resp = case["s"].get(f"/api/v1/revisions/{case['revision']}/document-checklist?operation=import&transport_mode=sea")
    assert resp.status_code == 200, resp.content
    status = {r["document_type"]: r["status"] for r in resp.json()["requirements"]}
    assert status == dict.fromkeys(("commercial_invoice", "insurance_invoice", "bill_of_lading"), "received_unverified")
    assert resp.json()["regulatory_validation"] is False
    # Types seulement détectés : ils restent proposés à la confirmation d'un agent.
    unclassified = resp.json()["unclassified_documents"]
    assert len(unclassified) == 3
    # Le type reconnu est proposé au classement avec le titre qui le justifie.
    by_type = {doc["detected_type"]: doc["type_evidence"] for doc in unclassified}
    assert by_type["insurance_invoice"]["method"] == "title"

    user = CaseDocument.objects.get(pk=links[INVOICE]["id"]).added_by
    result = intelligence.analyze(org=org, actor=user, revision_id=case["revision"])
    assert result["document_invoices"] == 2  # B/L et assurance citent IIC-2026-7784
    assert set(DocumentInvoiceLink.objects.values_list("status", flat=True)) == {"proposed"}
    shipment = Shipment.objects.get()
    assert shipment.reference == "MEDAF-BCN-OWD-2610052"
    assert shipment.document_links.count() == 3  # facture (« Related B/L »), B/L et assurance


def test_t57_declared_type_is_a_confirmation_and_unknown_type_is_refused(world, session):
    """LEC-07 : un type choisi au dépôt vaut confirmation signée ; un type inconnu est refusé."""
    call_command("seed_document_types")
    case = make_case(session, make_edition())
    link = upload(case, INSURANCE, document_type="insurance_invoice")
    assert link["usage"] == "insurance"
    assert link["document_type"] == {
        "code": "insurance_invoice",
        "label": TYPES["insurance_invoice"].fr,
        "label_en": "Insurance invoice",
        "source": "confirmed",
        "evidence": {"reason": "Type indiqué au dépôt."},
    }
    classification = DocumentClassification.objects.get(case_document_id=link["id"])
    assert classification.confirmed_by.email == "declarant@a.test"
    file = SimpleUploadedFile("x.pdf", (BATIPRO / BL).read_bytes(), content_type="application/pdf")
    resp = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "document_type": "nimporte"})
    assert resp.status_code == 422 and resp.json()["code"] == "UNKNOWN_DOCUMENT_TYPE"
    # Type confirmé sans lecture automatique : rien n'est deviné.
    other = upload(case, BL, document_type="packing_list", duplicate_action="keep_both")
    resp = case["s"].post(f"/api/v1/case-documents/{other['id']}/extractions", {})
    assert resp.status_code == 422 and resp.json()["code"] == "NO_READER_FOR_TYPE"


def test_t57_title_contradicting_the_agent_choice_is_shown_not_applied(world, session):
    """LEC-07 : une assurance déposée comme « Facture » reste lue comme facture, l'écart est signalé ;
    l'agent confirme le bon type et la lecture suit ce type."""
    call_command("seed_document_types")
    case = make_case(session, make_edition())
    link = upload(case, INSURANCE, usage="invoice")
    assert link["usage"] == "invoice" and link["document_type"] is None
    assert link["type_mismatch"]["code"] == "insurance_invoice"
    assert link["type_mismatch"]["evidence"]["excerpt"] == "FACTURE D ASSURANCE"
    resp = case["s"].post(
        f"/api/v1/case-documents/{link['id']}/confirm-type",
        {"document_type": "insurance_invoice", "reason": "Titre lu : FACTURE D ASSURANCE"},
    )
    assert resp.status_code == 201, resp.content
    run = read_piece(case, link)
    assert run.options["reader"] == "insurance" and run.invoice_id is None
    docs = case["s"].get(f"/api/v1/cases/{case['id']}/documents").json()["results"]
    assert docs[0]["type_mismatch"] is None and docs[0]["document_type"]["source"] == "confirmed"
