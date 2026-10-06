"""Lot 1, référentiel (jeu F) : T15, T29 (zéros), T30, T31, T32 et REC-01/02."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.tariffs.codes import normalize_code
from apps.tariffs.importers.csv_export import import_csv
from apps.tariffs.importers.pdf_text import import_pdf_text, split_pages
from apps.tariffs.models import (
    ImportIssue,
    LegalNote,
    NodeCorrection,
    PublicationState,
    RateObservation,
    RawTariffRecord,
    SourceDocument,
    TariffNode,
)
from apps.tariffs.services import compare_editions
from tests.conftest import PASSWORD

FIXTURES = Path(settings.BASE_DIR).parent / "fixtures" / "synthetic"


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def manager(db):
    return User.objects.create_user(email="ref@test.test", password=PASSWORD, is_reference_manager=True)


@pytest.fixture
def csv_edition(db):
    return import_csv(FIXTURES / "referentiel-f.csv", edition_label="Jeu F CSV", title="referentiel-f.csv")


@pytest.fixture
def text_edition(db):
    return import_pdf_text(FIXTURES / "referentiel-f.txt", edition_label="Jeu F texte", title="referentiel-f.txt")


def issues(edition, category):
    return ImportIssue.objects.filter(run=edition.import_run, category=category)


def node(edition, code):
    return TariffNode.objects.get(edition=edition, code=code)


# --- Normalisation des codes -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3004.90.00", "30049000"),
        ("0101 10 10", "01011010"),
        ("01011010", "01011010"),
        ("3004AB00", None),
        ("", None),
        ("010", "010"),
    ],
)
def test_normalize_code_keeps_zeros_and_never_repairs(raw, expected):
    assert normalize_code(raw) == expected


# --- Import CSV (T30, T31) ---------------------------------------------------


def test_csv_import_keeps_every_raw_row(csv_edition):
    run = csv_edition.import_run
    assert RawTariffRecord.objects.filter(run=run).count() == 8  # en-tête + 7 lignes, doublons compris
    assert run.source.is_derived_copy and run.source.kind == "csv_export"
    assert len(run.source.sha256) == 64
    assert csv_edition.publication_state == PublicationState.DRAFT
    assert csv_edition.effective_from is None and not csv_edition.applicability_verified
    record = node(csv_edition, "01011000").source_record
    assert record.cell_range == "A2:F2"
    assert record.raw_cells[0] == "01011000"


def test_csv_import_flags_malformed_and_duplicates_without_dedup(csv_edition):
    malformed = issues(csv_edition, "MALFORMED_CODE")
    assert {i.details["raw_code"] for i in malformed} == {"0101900", "3004AB00"}
    assert all(i.severity == "blocking" for i in malformed)
    assert not TariffNode.objects.filter(edition=csv_edition, code__in=["0101900", "3004AB00"]).exists()
    dup = issues(csv_edition, "DUPLICATE_CODE").get()
    assert dup.record.cell_range == "A4:F4"
    assert node(csv_edition, "01011000").occurrences.count() == 1
    assert node(csv_edition, "01011000").label_clean == "Chevaux reproducteurs de race pure (fictif)"


def test_csv_empty_cell_is_unknown_not_zero(csv_edition):
    obs = {o.column: o for o in node(csv_edition, "01019000").rate_observations.all()}
    assert obs["TVA"].quality == RateObservation.Quality.UNKNOWN and obs["TVA"].value is None
    zero = {o.column: o for o in node(csv_edition, "30049000").rate_observations.all()}
    assert zero["TVA"].quality == RateObservation.Quality.KNOWN and zero["TVA"].value == Decimal("0")


def test_csv_flags_non_numeric_column_and_damaged_labels(csv_edition):
    mismatch = issues(csv_edition, "COLUMN_CONTENT_MISMATCH").get()
    assert mismatch.details["column"] == "UNITE"
    damaged = node(csv_edition, "30049000")
    assert damaged.label_damaged and "�" in damaged.label_clean
    assert damaged.label_raw == "Autres m\x02dicaments fictifs"  # brut intact, aucune correction devinée
    assert issues(csv_edition, "ENCODING_DAMAGE").get().details["count"] == 2
    assert issues(csv_edition, "FORMULAS_UNAVAILABLE").exists()


def test_csv_builds_hierarchy_with_derived_parents(csv_edition):
    line = node(csv_edition, "01019000")
    assert [line.parent.code, line.parent.parent.code, line.parent.parent.parent.code] == ["010190", "0101", "01"]
    assert line.parent.validation_state == "derived" and not line.parent.declarable
    assert line.full_path_label == "01 › 01.01 › 0101.90 › Autres"


def test_reimport_creates_new_run_and_keeps_source(csv_edition):
    again = import_csv(FIXTURES / "referentiel-f.csv", edition_label="Jeu F CSV bis", title="referentiel-f.csv")
    assert again.import_run_id != csv_edition.import_run_id
    assert SourceDocument.objects.count() == 1
    assert TariffNode.objects.filter(edition=csv_edition).count() == TariffNode.objects.filter(edition=again).count()


# --- Import du texte extrait du PDF -------------------------------------------


def test_split_pages_convention():
    pages = split_pages((FIXTURES / "referentiel-f.txt").read_text(encoding="utf-8").replace("\r\n", "\n"))
    assert [(p, printed) for p, printed, _ in pages] == [(1, ""), (2, "1"), (3, "2"), (4, "3"), (5, "4")]


def test_text_import_pages_codes_notes_and_coverage(text_edition):
    run = text_edition.import_run
    assert run.coverage["pages_total"] == 5
    assert run.coverage["table_starts_at_page"] == 3
    assert run.coverage["pages_with_codes"] == 2
    lines = set(TariffNode.objects.filter(edition=text_edition, kind="tariff_line").values_list("code", flat=True))
    assert lines == {"01011010", "01011090", "01012000", "01021000", "01030000", "02013000"}
    line = node(text_edition, "01011010")
    assert line.source_record.page_index == 4 and line.source_record.printed_page == "3"
    assert line.label_clean == ""  # aucune désignation associée sans coordonnées
    notes = {(n.scope_type, n.scope_ref): n.text_raw for n in LegalNote.objects.filter(edition=text_edition)}
    assert "exclut les poissons" in notes[("chapter", "01")]
    assert "Note de section fictive" in notes[("section", "I")]
    assert issues(text_edition, "LABELS_AND_RATES_NOT_ASSOCIATED").exists()


def test_text_import_anomalies(text_edition):
    mismatch = issues(text_edition, "HEADING_MISMATCH").get()
    assert mismatch.details["code"] == "01012000" and mismatch.details["read_under"] == "0102"
    assert issues(text_edition, "DUPLICATE_CODE").get().details["code"] == "01021000"
    assert issues(text_edition, "MALFORMED_CODE").get().details["raw_code"] == "01023.00"
    assert issues(text_edition, "TRAILING_PUNCTUATION").get().details["raw_code"] == "0103.00.00."
    implicit = node(text_edition, "0103")
    assert implicit.validation_state == "derived" and implicit.parent.code == "01"


def test_compare_editions_records_divergences_both_ways(csv_edition, text_edition):
    summary = compare_editions(reference=text_edition, other=csv_edition)
    assert summary == {"common": 1, "only_reference": 5, "only_other": 3}
    divergences = ImportIssue.objects.filter(category="SOURCE_DIVERGENCE")
    assert divergences.count() == 8
    assert {d.details["code"] for d in divergences if d.details["present_in"] == str(csv_edition.id)} == {
        "01011000",
        "01019000",
        "30049000",
    }


# --- API : publication, recherche, fiche, preuve (T15, T32, REC-01/02) -------


def publish(session_factory, edition):
    s = session_factory("ref@test.test")
    resp = s.post(f"/api/v1/tariffs/editions/{edition.id}/publish", {"mode": "consultation"})
    assert resp.status_code == 200, resp.content
    return s


def test_draft_is_invisible_until_published(world, manager, csv_edition, session):
    user = session("declarant@a.test")
    assert user.get("/api/v1/tariffs/editions").json() == []
    assert user.get("/api/v1/tariffs/search", q="01011000").json()["results"] == []
    assert user.get(f"/api/v1/tariffs/nodes/{node(csv_edition, '01011000').id}").status_code == 404
    publish(session, csv_edition)
    editions = user.get("/api/v1/tariffs/editions").json()
    assert editions[0]["publication_state"] == "consultation"
    assert "Consultation historique" in editions[0]["warning"]


def test_only_reference_manager_publishes_or_resolves(world, manager, csv_edition, session):
    s = session("admin@a.test")
    assert s.post(f"/api/v1/tariffs/editions/{csv_edition.id}/publish", {"mode": "consultation"}).status_code == 403
    issue = issues(csv_edition, "DUPLICATE_CODE").get()
    resp = s.post(f"/api/v1/reference-issues/{issue.id}/resolve", {"resolution": "accepted", "reason": "x"})
    assert resp.status_code == 403
    assert s.get("/api/v1/reference-imports").status_code == 403


def test_operational_publication_is_refused_with_reasons(manager, csv_edition, session):
    resp = session("ref@test.test").post(f"/api/v1/tariffs/editions/{csv_edition.id}/publish", {"mode": "operational"})
    assert resp.status_code == 422
    missing = resp.json()["details"]["missing"]
    assert "date d'effet vérifiée" in missing and any("copie dérivée" in m for m in missing)
    csv_edition.refresh_from_db()
    assert csv_edition.publication_state == PublicationState.DRAFT


def test_search_exact_prefix_text_and_trigram(world, manager, csv_edition, text_edition, session):
    publish(session, csv_edition)
    publish(session, text_edition)
    s = session("declarant@a.test")

    exact = s.get("/api/v1/tariffs/search", q="0101.10.00").json()["results"]
    assert [(r["code"], r["reason"]) for r in exact] == [("01011000", "code exact")]

    prefix = s.get("/api/v1/tariffs/search", q="0101").json()["results"]
    assert prefix[0]["reason"] == "code exact"
    assert {r["code"] for r in prefix if r["reason"] == "préfixe"} >= {"01011000", "01011010", "01019000"}

    text = s.get("/api/v1/tariffs/search", q="chevaux").json()["results"]
    assert text[0]["code"] == "01011000" and text[0]["reason"] == "texte"

    fuzzy = s.get("/api/v1/tariffs/search", q="chevals reproducteur").json()["results"]
    assert any(r["code"] == "01011000" for r in fuzzy)

    zeros = s.get("/api/v1/tariffs/search", q="02013000").json()["results"]
    assert zeros[0]["code"] == "02013000"  # code textuel : le zéro initial reste


def test_autres_shows_parents_and_edition(world, manager, csv_edition, session):
    publish(session, csv_edition)
    s = session("declarant@a.test")
    result = s.get("/api/v1/tariffs/search", q="autres", edition_id=str(csv_edition.id)).json()["results"]
    autres = next(r for r in result if r["code"] == "01019000")
    assert autres["full_path"] == "01 › 01.01 › 0101.90 › Autres"
    assert autres["edition"]["label"] == "Jeu F CSV"
    detail = s.get(f"/api/v1/tariffs/nodes/{autres['id']}").json()
    assert [a["code"] for a in detail["ancestors"]] == ["01", "0101", "010190"]
    assert detail["ancestors"][0]["label"] == ""  # parent sans libellé dans cette source : non inventé


def test_node_detail_with_evidence_notes_rates_and_cross_edition(world, manager, csv_edition, text_edition, session):
    publish(session, csv_edition)
    publish(session, text_edition)
    s = session("declarant@a.test")
    detail = s.get(f"/api/v1/tariffs/nodes/{node(csv_edition, '01019000').id}").json()
    assert detail["evidence"]["cell_range"] == "A3:F3"
    rates = {r["column"]: r for r in detail["rate_observations"]["items"]}
    assert rates["TVA"] == {"column": "TVA", "raw_value": "", "value": None, "quality": "unknown"}
    assert rates["DDI"]["value"] == "30"
    assert "≠ 0" in detail["rate_observations"]["warning"]
    assert any("exclut les poissons" in n["text"] for n in detail["related_notes"])
    assert detail["edition"]["source"]["is_derived_copy"] is True

    line = s.get(f"/api/v1/tariffs/nodes/{node(text_edition, '01012000').id}").json()
    assert line["evidence"]["page_index"] == 4 and line["evidence"]["printed_page"] == "3"
    assert any(i["category"] == "HEADING_MISMATCH" for i in line["issues"])
    assert any("exclut les poissons" in n["text"] for n in line["notes"])

    record = s.get(f"/api/v1/tariffs/records/{line['evidence']['record_id']}").json()
    assert "0101.20.00" in record["raw_text"]


def test_resolve_issue_correction_is_separate_from_raw(world, manager, csv_edition, session):
    s = session("ref@test.test")
    target = node(csv_edition, "30049000")
    issue = issues(csv_edition, "DAMAGED_LABEL").get(node=target)
    resp = s.post(
        f"/api/v1/reference-issues/{issue.id}/resolve",
        {
            "resolution": "corrected",
            "reason": "Accent restitué d'après le PDF",
            "evidence": "PDF p. 210",
            "correction": {"field": "label_clean", "value": "Autres médicaments fictifs"},
        },
    )
    assert resp.status_code == 200, resp.content
    target.refresh_from_db()
    assert target.label_clean == "Autres médicaments fictifs" and target.label_raw == "Autres m\x02dicaments fictifs"
    correction = NodeCorrection.objects.get(node=target)
    assert correction.previous.startswith("Autres m") and correction.actor.email == "ref@test.test"
    assert AuditEvent.objects.filter(event_type="tariff.node_corrected").exists()

    no_reason = s.post(
        f"/api/v1/reference-issues/{issues(csv_edition, 'DUPLICATE_CODE').get().id}/resolve",
        {"resolution": "accepted", "reason": " "},
    )
    assert no_reason.status_code == 400


def test_published_edition_is_immutable_and_withdrawal_keeps_history(world, manager, csv_edition, session):
    s = publish(session, csv_edition)
    target = node(csv_edition, "01011000")
    issue = ImportIssue.objects.create(
        run=csv_edition.import_run, node=target, category="X", severity="review", message="test"
    )
    resp = s.post(
        f"/api/v1/reference-issues/{issue.id}/resolve",
        {
            "resolution": "corrected",
            "reason": "r",
            "evidence": "e",
            "correction": {"field": "label_clean", "value": "modifié"},
        },
    )
    assert resp.status_code == 409 and resp.json()["code"] == "EDITION_IMMUTABLE"

    assert s.post(f"/api/v1/tariffs/editions/{csv_edition.id}/withdraw", {"reason": "remplacée"}).status_code == 200
    user = session("declarant@a.test")
    assert user.get("/api/v1/tariffs/search", q="01011000").json()["results"] == []
    assert user.get(f"/api/v1/tariffs/nodes/{target.id}").status_code == 200  # historique consultable


def test_reference_manager_lists_runs_and_issues(manager, csv_edition, session):
    s = session("ref@test.test")
    runs = s.get("/api/v1/reference-imports").json()["results"]
    assert runs[0]["open_issues"] == ImportIssue.objects.filter(run=csv_edition.import_run).count()
    listed = s.get(f"/api/v1/reference-imports/{runs[0]['id']}/issues", severity="blocking").json()["results"]
    assert {i["category"] for i in listed} == {"MALFORMED_CODE"}
    assert listed[0]["evidence"]["cell_range"].startswith("A")
