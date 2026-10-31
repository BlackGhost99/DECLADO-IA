"""T79 : préparation automatique du dossier après la lecture d'une facture.

Pièces fictives (apps/extraction/synthetic.py). Rien n'est inventé : l'origine n'est reprise que
si la facture l'imprime ; date, régime et édition sont des propositions « à confirmer ».
"""

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.cases import autoprep
from apps.extraction import synthetic
from apps.extraction.models import ExtractionRun
from tests.test_extraction import extracted, make_edition


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def new_case(s, **extra):
    resp = s.post("/api/v1/cases", {"title": "Préparation", **extra})
    assert resp.status_code == 201, resp.content
    body = resp.json()
    return {"s": s, "id": body["id"], "revision": body["revision"]["id"]}


def detail(case):
    return case["s"].get(f"/api/v1/revisions/{case['revision']}").json()


@pytest.fixture
def prepared(world, session):
    edition = make_edition()
    s = session("declarant@a.test")
    earlier = new_case(s)
    assert s.patch(f"/api/v1/revisions/{earlier['revision']}", {"regime": "IM4", "row_version": 1}).status_code == 200
    return {"edition": edition, "case": new_case(s)}


def test_reading_fills_edition_date_regime_and_prepares_checked_goods(prepared):
    case, edition = prepared["case"], prepared["edition"]
    _link, run = extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    assert run["status"] == "succeeded"
    rev = detail(case)
    assert rev["target_edition"]["id"] == str(edition.id)
    assert rev["planned_declaration_date"] == timezone.localdate().isoformat()
    assert rev["regime"] == "IM4"
    assert sorted(rev["prefilled"]) == ["planned_declaration_date", "regime", "target_edition"]
    # Une marchandise par ligne, origine reprise de la ligne, code contrôlé contre l'édition.
    goods = rev["goods_lines"]
    assert [(g["description"], g["origin_country"]) for g in goods] == [
        ("Chevaux reproducteurs fictifs", "FR"),
        ("Selles en cuir fictives", "IT"),
    ]
    assert all(g["latest_check"] and g["latest_check"]["is_current"] for g in goods)
    blocking = {(b["field"], b["message"]) for b in rev["completeness"]["blocking"]}
    assert not any(f in ("planned_declaration_date", "regime", "target_edition", "goods_lines") for f, _m in blocking)
    warnings = " ".join(w["message"] for w in rev["completeness"]["warnings"])
    assert "Proposé automatiquement, à confirmer" in warnings and "régime (repris du dernier dossier)" in warnings
    event = AuditEvent.objects.get(event_type="revision.prepared_automatically")
    assert event.current["goods_created"] == 2 and event.current["codes_checked"] == 2
    assert event.actor.email == "declarant@a.test"


def test_saving_a_proposed_field_confirms_it_and_nothing_is_overwritten(prepared):
    case = prepared["case"]
    s = case["s"]
    assert s.patch(f"/api/v1/revisions/{case['revision']}", {"regime": "IM7", "row_version": 1}).status_code == 200
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    rev = detail(case)
    assert rev["regime"] == "IM7" and "regime" not in rev["prefilled"]
    resp = s.patch(
        f"/api/v1/revisions/{case['revision']}",
        {"planned_declaration_date": rev["planned_declaration_date"], "row_version": rev["row_version"]},
    )
    assert resp.status_code == 200, resp.content
    assert detail(case)["prefilled"] == ["target_edition"]


def test_origin_is_taken_only_from_the_document_never_guessed(prepared):
    case = prepared["case"]
    lines = [{k: v for k, v in line.items() if k != "origin"} for line in synthetic.SIMPLE_LINES]
    cols = [c for c in synthetic.HEADER if c != "origin"]
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf(lines, columns=cols))
    rev = detail(case)
    assert rev["origin_country"] == ""
    assert [g["origin_country"] for g in rev["goods_lines"]] == ["", ""]
    assert sum(b["field"] == "origin_country" for b in rev["completeness"]["blocking"]) == 2

    # L'agent saisit l'origine du dossier une fois : elle vaut pour les marchandises sans origine,
    # et les lignes facturées rattachées ne sont plus signalées.
    resp = case["s"].patch(
        f"/api/v1/revisions/{case['revision']}", {"origin_country": "cn", "row_version": rev["row_version"]}
    )
    assert resp.status_code == 200, resp.content
    rev = detail(case)
    assert [g["origin_country"] for g in rev["goods_lines"]] == ["CN", "CN"]
    assert not [b for b in rev["completeness"]["blocking"] if b["field"] == "origin_country"]
    assert AuditEvent.objects.filter(event_type="goods_line.origin_from_case").count() == 1


def test_printed_country_of_origin_fills_the_case_and_its_goods(prepared):
    case = prepared["case"]
    lines = [{k: v for k, v in line.items() if k != "origin"} for line in synthetic.SIMPLE_LINES]
    cols = [c for c in synthetic.HEADER if c != "origin"]
    header = synthetic._header_block() + [(300, 104, "Country of origin : China")]
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf(lines, columns=cols, header=header))
    rev = detail(case)
    assert rev["origin_country"] == "CN" and "origin_country" not in rev["prefilled"]
    assert [g["origin_country"] for g in rev["goods_lines"]] == ["CN", "CN"]
    event = AuditEvent.objects.get(event_type="revision.prepared_automatically")
    assert "China" in event.current["origin_evidence"]


def test_made_in_is_used_only_when_the_document_names_one_country(prepared):
    case = prepared["case"]
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    run = ExtractionRun.objects.get()
    run.read_text = "Selles fictives\nMade in Italy\n"
    assert autoprep.printed_origin(run) == ("IT", "« Made in Italy » imprimé sur la facture")
    run.read_text = "Made in Italy\nMade in China\n"
    assert autoprep.printed_origin(run) == ("", "")


def test_validated_revision_is_not_touched(prepared):
    case = prepared["case"]
    _link, _run = extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    run = ExtractionRun.objects.get()
    rev = run.invoice.revision
    rev.state = rev.State.VALIDATED
    rev.save(update_fields=["state"])
    assert autoprep.after_invoice_read(run, run.invoice) == {}


def test_missing_regime_is_reported_once_for_the_case(world, session):
    make_edition()
    case = new_case(session("declarant@a.test"))  # aucun dossier antérieur : pas de régime à reprendre
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf())
    rev = detail(case)
    assert rev["regime"] == "" and len(rev["goods_lines"]) == 2
    regime = [b for b in rev["completeness"]["blocking"] if b["field"] == "regime"]
    assert [(b["scope"], b["message"]) for b in regime] == [("revision", "Régime douanier à renseigner.")]


def test_controls_do_not_repeat_what_is_already_reported(prepared):
    """Code déjà contrôlé sur la marchandise, réf. facultative, origine du dossier : pas de doublon."""
    case = prepared["case"]
    extracted(case, "codes.pdf", synthetic.code_cases_pdf())
    rev = detail(case)
    warnings = rev["completeness"]["warnings"]
    assert not [w for w in warnings if w["scope"] == "invoice_line" and w["field"].startswith("code:")]
    assert not [w for w in warnings if w["field"] == "source_reference"]
    for w in warnings:
        if w["message"].startswith("À vérifier") and w["scope"] == "invoice_line":
            assert w["message"].startswith("À vérifier (")


def test_buyer_matching_a_known_client_becomes_the_proposed_importer(prepared, world):
    """Nom identique (casse et ponctuation ignorées) d'un client de la société : proposé, à confirmer.
    Un acheteur inconnu n'est jamais créé : il est seulement cité dans le manque à combler."""
    case = prepared["case"]
    header = synthetic._header_block() + [(300, 56, "Client : IMPORTATEUR A.")]
    extracted(case, "facture.pdf", synthetic.simple_invoice_pdf(header=header))
    s = case["s"]
    body = s.get(f"/api/v1/cases/{case['id']}").json()
    assert body["importer"]["id"] == str(world["importer_a"].id)
    rev = detail(case)
    assert "importer" in rev["prefilled"]
    assert not [b for b in rev["completeness"]["blocking"] if b["field"] == "importer"]
    resp = s.patch(
        f"/api/v1/cases/{case['id']}",
        {"importer_id": str(world["importer_a"].id), "row_version": body["row_version"]},
    )
    assert resp.status_code == 200, resp.content
    assert "importer" not in detail(case)["prefilled"]

    other = new_case(s)
    header = synthetic._header_block() + [(300, 56, "Client : Acheteur Inconnu SA")]
    extracted(other, "facture.pdf", synthetic.simple_invoice_pdf(header=header))
    assert s.get(f"/api/v1/cases/{other['id']}").json()["importer"] is None
    [missing] = [b for b in detail(other)["completeness"]["blocking"] if b["field"] == "importer"]
    assert "Acheteur Inconnu SA" in missing["message"]
