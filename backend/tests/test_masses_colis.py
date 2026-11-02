"""Colis et masse brute lus sur le titre de transport, repris au DAU (cases 23 à 25, 35, 39) et à l'écran.

Jeu BatiPro fictif : le connaissement imprime « 9 caisses bois » et « 3 940 kg ». Rien n'est deviné :
une autre unité, un titre non lu ou plusieurs articles laissent les cases vides.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.cases.measures import packages, weight_kg
from tests.test_exports import pdf_text
from tests.test_extraction import make_case, make_edition
from tests.test_lecture_pieces import BL, INVOICE, read_piece, upload


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def test_weights_are_kept_only_in_kilograms_and_packages_need_a_count():
    assert weight_kg("3 940 kg") == Decimal("3940")
    assert weight_kg("18,450.50 KGS") == Decimal("18450.50")
    assert weight_kg("3 940,5 kilos") == Decimal("3940.5")
    assert weight_kg("3.94 t") is None and weight_kg("8 700 lbs") is None and weight_kg("") is None
    assert weight_kg("1.234 kg") is None  # milliers ou décimales ? on ne tranche pas
    assert packages("9 caisses bois") == (9, "caisses bois")
    assert packages("1 200 cartons") == (1200, "cartons")
    assert packages("PALLETS") == (None, "") and packages("0 colis") == (None, "")


def test_t85_bl_measures_fill_the_dau_and_the_export_screen(world, session):
    call_command("seed_document_types")
    case = make_case(session, make_edition())
    before = case["s"].get(f"/api/v1/cases/{case['id']}").json()["revision"]["measures"]
    assert before == {"net_weight_kg": None, "packages": None, "nature": "", "gross_weight_kg": None, "sources": []}
    links = {name: upload(case, name, usage="auto") for name in (INVOICE, BL)}
    for link in links.values():
        read_piece(case, link)
    measures = case["s"].get(f"/api/v1/cases/{case['id']}").json()["revision"]["measures"]
    assert measures == {
        "net_weight_kg": None,
        "packages": 9,
        "nature": "caisses bois",
        "gross_weight_kg": "3940",
        "sources": ["MEDAF-BCN-OWD-2610052"],
    }
    resp = case["s"].post(f"/api/v1/cases/{case['id']}/exports", {"format": "pdf"})
    assert resp.status_code == 201, resp.content
    raw = case["s"].get(f"/api/v1/cases/{case['id']}/exports/{resp.json()['id']}/file")
    text = " ".join(pdf_text(b"".join(raw.streaming_content)).replace(" ", " ").split())
    assert "caisses bois" in text and "3 940" in text
    # Plusieurs articles : la masse reste au total (case 25), jamais répartie entre les articles.
    from apps.cases.dau import data
    from apps.cases.models import CustomsCase

    c = CustomsCase.objects.get(pk=case["id"])
    d = data(c, c.current_revision, {"articles": []})
    assert d["packages"] == "9" and d["gross_weight"] == "3 940"
    if len(d["goods"]) > 1:
        assert all(g["gross"] == "" and g["marks"] == "" for g in d["goods"])


def test_t85_a_single_article_carries_the_packages_and_gross_weight(world, session):
    from apps.cases.dau import data
    from apps.cases.models import CustomsCase
    from tests.test_validation import complete, ready_case

    call_command("seed_document_types")
    edition = make_edition()
    case, _ = ready_case(session, edition)
    complete(case, world, edition)
    read_piece(case, upload(case, BL, usage="auto"))
    c = CustomsCase.objects.get(pk=case["id"])
    [article] = data(c, c.current_revision, {"articles": []})["goods"]
    assert article["marks"] == "9 caisses bois" and article["gross"] == "3 940"
