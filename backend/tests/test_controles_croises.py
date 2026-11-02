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


def gaps(case):
    """Écarts entre pièces, hors chiffre de contrôle : le B/L BatiPro fictif imprime « MSCU 771205-4 »,
    dont le chiffre de contrôle ISO 6346 serait 0 (vérifié par T102)."""
    return [w for w in cross(case)[0] if "ISO 6346" not in w["message"]]


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
    assert gaps(batipro) == []
    generated(batipro, "colisage.pdf", synthetic.packing_list_pdf())
    assert gaps(batipro) == []


def test_t88_a_piece_citing_another_invoice_is_flagged_not_blocking(batipro):
    generated(batipro, "colisage-autre.pdf", synthetic.packing_list_pdf(invoice="TXS-2026-0001", gross="4 100 kg"))
    rev = cross(batipro)[1]
    warnings = gaps(batipro)
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


def test_t89_origin_certificate_fills_goods_without_origin_whatever_the_reading_order(world, session):
    """Certificat lu avant ou après la facture : l'origine des marchandises sans origine est reprise."""
    from apps.audit.models import AuditEvent

    call_command("seed_document_types")
    case = make_case(session, make_edition())
    # Facture fictive sans pays d'origine imprimé : seule la preuve du certificat compte.
    generated(case, "origine.pdf", synthetic.origin_certificate_pdf(invoice="F-2026-001", country="China"))
    columns = [c for c in synthetic.HEADER if c != "origin"]
    generated(case, "facture.pdf", synthetic.simple_invoice_pdf(columns=columns))
    rev = cross(case)[1]
    assert rev["origin_country"] == ""
    assert rev["goods_lines"] and {g["origin_country"] for g in rev["goods_lines"]} == {"CN"}
    assert cross(case)[0] == []  # origine identique : aucun écart
    event = AuditEvent.objects.get(event_type="goods_line.origin_from_certificate")
    assert event.current["origin_country"] == "CN" and "origine.pdf" in event.current["evidence"]


def test_t89_a_certificate_for_another_invoice_or_contradicting_ones_fill_nothing(world, session):
    call_command("seed_document_types")
    edition = make_edition()
    case, _ = ready_case(session, edition)
    s = case["s"]
    detail = complete(case, world, edition)
    goods = detail["revision"]["goods_lines"][0]
    resp = s.patch(f"/api/v1/goods-lines/{goods['id']}", {"origin_country": "", "row_version": goods["row_version"]})
    assert resp.status_code == 200, resp.content
    generated(case, "autre.pdf", synthetic.origin_certificate_pdf(invoice="X-999", country="Spain"))
    assert cross(case)[1]["goods_lines"][0]["origin_country"] == ""
    generated(case, "es.pdf", synthetic.origin_certificate_pdf(invoice="F-1", country="Spain"))
    assert cross(case)[1]["goods_lines"][0]["origin_country"] == "ES"


def test_t101_container_and_seal_compared_between_bill_of_lading_and_packing_list(batipro):
    # Même conteneur (chiffre de contrôle omis) et même scellé : rien à signaler.
    generated(batipro, "colisage.pdf", synthetic.packing_list_pdf(container="MSCU 771205"))
    assert gaps(batipro) == []
    bl = next(
        d for d in batipro["s"].get(f"/api/v1/cases/{batipro['id']}/documents").json()["results"]
        if d["usage"] == "transport"
    )  # fmt: skip
    fields = {f["field"]: f for f in bl["latest_extraction"]["fields"]}
    assert fields["seal"]["raw"] == "ES449201"


def test_t101_other_container_and_seal_are_flagged_not_blocking(batipro):
    generated(batipro, "colisage-autre.pdf", synthetic.packing_list_pdf(container="TGHU 123456-7", seal="XX000111"))
    rev = cross(batipro)[1]
    by_field = {(w["field"], w["label"].split(" ")[0]): w["message"] for w in gaps(batipro)}
    pl_container = next(m for (f, label), m in by_field.items() if f == "container" and label == "Liste")
    assert "TGHU 123456-7" in pl_container and "MSCU 771205-4" in pl_container
    bl_container = next(m for (f, label), m in by_field.items() if f == "container" and label != "Liste")
    assert "MSCU 771205-4" in bl_container and "absent de la liste de colisage" in bl_container
    seal = next(m for (f, _label), m in by_field.items() if f == "seal")
    assert "XX000111" in seal and "ES449201" in seal
    assert not any(b["scope"] == "case_document" for b in rev["completeness"]["blocking"])


def test_t102_container_check_digit_flags_a_misread_or_misprinted_number(batipro):
    from apps.cases.crosschecks import check_digit

    assert check_digit("CSQU 305438") == 3 and check_digit("MSCU771205") == 0 and check_digit("12345") is None
    [bl] = [w for w in cross(batipro)[0] if w["field"] == "container"]
    assert bl["label"].startswith("Document de transport")
    assert "MSCU 771205-4 (attendu : 0)" in bl["message"] and "mal lu ou mal imprimé" in bl["message"]
    generated(batipro, "colisage.pdf", synthetic.packing_list_pdf(container="MSCU 771205-0"))
    flagged = [w["label"] for w in cross(batipro)[0] if "ISO 6346" in w["message"]]
    assert len(flagged) == 1 and flagged[0].startswith("Document de transport")  # la liste est juste


def test_t102_packages_compared_between_the_bill_of_lading_and_its_packing_list(batipro):
    generated(batipro, "colisage.pdf", synthetic.packing_list_pdf(packages="8 caisses bois"))
    [warning] = gaps(batipro)
    assert warning["field"] == "packages" and warning["label"].startswith("Liste de colisage")
    assert warning["message"] == "8 colis, le titre de transport en indique 9."


def test_t102_several_packing_lists_are_summed_against_the_single_bill_of_lading(batipro):
    generated(
        batipro, "colisage-1.pdf", synthetic.packing_list_pdf(number="PL-FIC-1", packages="5 caisses", gross="2 000 kg")
    )
    file = SimpleUploadedFile(
        "colisage-2.pdf",
        synthetic.packing_list_pdf(number="PL-FIC-2", packages="4", gross="1 940 kg"),
        content_type="application/pdf",
    )
    resp = batipro["s"].upload(f"/api/v1/cases/{batipro['id']}/documents", {"file": file, "usage": "packing_list"})
    assert resp.status_code == 201, resp.content
    # La seconde liste n'est pas encore lue : une somme partielle n'est pas comparée.
    assert gaps(batipro) == []
    read_piece(batipro, resp.json())
    assert gaps(batipro) == []  # 5 + 4 colis, 2 000 + 1 940 kg : conforme au B/L
    generated(batipro, "colisage-3.pdf", synthetic.packing_list_pdf(number="PL-FIC-3", packages="1", gross="60 kg"))
    rev = cross(batipro)[1]
    messages = {w["field"]: w for w in gaps(batipro)}
    assert messages["gross_weight"]["message"] == "Masse brute 3940 kg, les 3 listes de colisage totalisent 4000 kg."
    assert (
        messages["packages"]["message"]
        == "9 colis sur le titre de transport, les 3 listes de colisage en totalisent 10."
    )
    assert messages["packages"]["label"].startswith("Document de transport")
    assert not any(b["scope"] == "case_document" for b in rev["completeness"]["blocking"])
