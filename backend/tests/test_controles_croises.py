"""Contrôles croisés entre pièces (T88) : écarts signalés à vérifier, jamais bloquants, jamais devinés.

Jeu BatiPro fictif et pièces générées (apps/extraction/synthetic.py).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.extraction import synthetic
from tests.test_extraction import make_case, make_edition
from tests.test_lecture_pieces import BL, INSURANCE, INVOICE, read_piece, upload
from tests.test_validation import complete, ready_case


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def cross(case):
    rev = case["s"].get(f"/api/v1/cases/{case['id']}").json()["revision"]
    return [w for w in rev["completeness"]["warnings"] if w["scope"] == "case_document"], rev


def generated(case, name, content):
    file = SimpleUploadedFile(name, content, content_type="application/pdf")
    resp = case["s"].upload(f"/api/v1/cases/{case['id']}/documents", {"file": file, "usage": "auto"})
    assert resp.status_code == 201, resp.content
    return read_piece(case, resp.json())


@pytest.fixture
def batipro(world, session):
    call_command("seed_document_types")
    case = make_case(session, make_edition())
    for name in (INVOICE, BL, INSURANCE):
        read_piece(case, upload(case, name, usage="auto"))
    return case


def test_t88_consistent_pieces_raise_nothing(batipro):
    warnings, rev = cross(batipro)
    assert warnings == []
    generated(batipro, "colisage.pdf", synthetic.packing_list_pdf())
    assert cross(batipro)[0] == []


def test_t88_a_piece_citing_another_invoice_is_flagged_not_blocking(batipro):
    generated(batipro, "colisage-autre.pdf", synthetic.packing_list_pdf(invoice="TXS-2026-0001", gross="4 100 kg"))
    warnings, rev = cross(batipro)
    messages = {w["field"]: w["message"] for w in warnings}
    assert "TXS-2026-0001" in messages["related_invoice"] and "absente du dossier" in messages["related_invoice"]
    assert "4100 kg" in messages["gross_weight"] and "3940 kg" in messages["gross_weight"]
    assert all(w["label"].startswith("Liste de colisage") for w in warnings)
    assert not any(b["scope"] == "case_document" for b in rev["completeness"]["blocking"])


def test_t88_insured_value_below_the_invoice_total_in_the_same_currency(batipro):
    rev = cross(batipro)[1]
    [invoice] = rev["invoices"]
    insured = next(
        f
        for d in batipro["s"].get(f"/api/v1/cases/{batipro['id']}/documents").json()["results"]
        if d["usage"] == "insurance"
        for f in d["latest_extraction"]["fields"]
        if f["field"] == "currency"
    )
    resp = batipro["s"].patch(f"/api/v1/invoices/{invoice['id']}",
                              {"declared_total": "25000", "currency": insured["parsed"] or insured["raw"],
                               "correction_reason": "Essai fictif", "row_version": invoice["row_version"]})  # fmt: skip
    assert resp.status_code == 200, resp.content
    messages = [w["message"] for w in cross(batipro)[0]]
    assert any("Valeur assurée 20500" in m and "inférieure au total des factures 25000" in m for m in messages)


def test_t88_origin_certificate_differing_from_the_goods_origin(world, session):
    call_command("seed_document_types")
    edition = make_edition()
    case, _ = ready_case(session, edition)
    complete(case, world, edition)  # marchandise d'origine FR, facture F-1
    generated(case, "origine.pdf", synthetic.origin_certificate_pdf(invoice="F-1", country="Spain"))
    messages = {w["field"]: w["message"] for w in cross(case)[0]}
    assert messages == {"country_of_origin": "Le certificat indique l'origine ES, différente de marchandise 1 : FR."}
    generated(case, "origine-fr.pdf", synthetic.origin_certificate_pdf(invoice="F-1", country="France"))
    assert len(cross(case)[0]) == 1  # le certificat conforme n'ajoute rien
