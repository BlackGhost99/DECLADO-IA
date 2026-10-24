"""P0: fail-closed uploads and precise human-verified document taxonomy."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.documents import antivirus
from apps.documents.models import Document
from apps.documents.synthetic import make_pdf
from apps.regulations.taxonomy import LEGACY_UNAMBIGUOUS, TYPES


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def case(world, session):
    s = session("declarant@a.test")
    created = s.post("/api/v1/cases", {"title": "P0 sécurité"})
    assert created.status_code == 201
    return s, created.json()["id"]


def upload(session, case_id, **extra):
    data = {"file": SimpleUploadedFile("invoice.pdf", make_pdf(["Facture fictive P0"]), content_type="application/pdf")}
    data.update(extra)
    return session.upload(f"/api/v1/cases/{case_id}/documents", data)


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (antivirus.MalwareDetected("test"), 422, "MALWARE_DETECTED"),
        (antivirus.ScanUnavailable("test"), 503, "MALWARE_SCAN_UNAVAILABLE"),
    ],
)
def test_no_document_leaves_quarantine_on_scan_failure(case, settings, monkeypatch, exception, status, code):
    def fail(_path):
        raise exception

    monkeypatch.setattr(antivirus, "scan_file", fail)
    s, cid = case
    response = upload(s, cid)
    assert response.status_code == status, response.content
    assert response.json()["code"] == code
    assert Document.objects.count() == 0
    for folder in ("quarantine", "documents"):
        root = settings.PRIVATE_STORAGE_ROOT / folder
        assert not root.exists() or not list(root.rglob("*.*")) and not any(p.is_file() for p in root.rglob("*"))


def test_document_type_is_explicit_and_not_confused_with_commercial_invoice(case):
    s, cid = case
    response = upload(s, cid, document_type_code="freight_invoice")
    assert response.status_code == 201, response.content
    link = response.json()
    assert link["document_type_code"] == "freight_invoice"
    assert link["usage"] == "other"
    assert link["document"]["sha256"]
    classify = s.patch(
        f"/api/v1/case-documents/{link['id']}/classify",
        {"document_type_code": "bill_of_lading"},
    )
    assert classify.status_code == 200, classify.content
    assert classify.json()["usage"] == "transport"
    assert classify.json()["document_type_code"] == "bill_of_lading"
    assert AuditEvent.objects.filter(event_type="case.document_classified").count() == 1
    replacement = s.upload(
        f"/api/v1/case-documents/{link['id']}/replace",
        {"file": SimpleUploadedFile("v2.pdf", make_pdf(["Document fictif v2"]), content_type="application/pdf")},
    )
    assert replacement.status_code == 201, replacement.content
    assert replacement.json()["document_type_code"] == "bill_of_lading"


def test_document_type_mismatch_and_unknown_code_fail_before_upload(case):
    s, cid = case
    mismatch = upload(s, cid, document_type_code="freight_invoice", usage="invoice")
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "DOCUMENT_TYPE_USAGE_MISMATCH"
    unknown = upload(s, cid, document_type_code="not_a_document_type")
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "INVALID_DOCUMENT_TYPE"
    assert Document.objects.count() == 0


def test_taxonomy_visible_to_authenticated_tenant_and_no_automatic_transport_inference(case, session):
    s, _ = case
    resp = s.get("/api/v1/document-types")
    assert resp.status_code == 200
    assert len(resp.json()["types"]) == len(TYPES)
    assert "invoice" not in LEGACY_UNAMBIGUOUS
    assert "transport" not in LEGACY_UNAMBIGUOUS
    assert session().get("/api/v1/document-types").status_code in (401, 403)
