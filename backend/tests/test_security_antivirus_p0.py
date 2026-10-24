"""Two security layers: ClamAV and application-level format/isolation controls."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.documents import antivirus
from apps.documents.models import Document
from apps.documents.synthetic import make_pdf, make_png

EICAR = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}"
    b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


@pytest.fixture(autouse=True)
def temporary_private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


@pytest.fixture
def workspace(world, session):
    client = session("declarant@a.test")
    case = client.post("/api/v1/cases", {"title": "Scan P0"})
    assert case.status_code == 201
    return client, case.json()["id"]


def upload(client, case_id, name, contents, content_type="application/pdf"):
    file = SimpleUploadedFile(name, contents, content_type=content_type)
    return client.upload(f"/api/v1/cases/{case_id}/documents", {"file": file})


def all_files(folder: Path):
    return [p for p in folder.rglob("*") if p.is_file()] if folder.exists() else []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (antivirus.ScanUnavailable("non joignable"), 503, "MALWARE_SCAN_UNAVAILABLE"),
        (antivirus.MalwareDetected("test"), 422, "MALWARE_DETECTED"),
    ],
)
def test_scanner_failure_is_fail_closed(workspace, settings, monkeypatch, error, expected_status, expected_code):
    def reject(_path):
        raise error

    monkeypatch.setattr(antivirus, "scan_file", reject)
    client, case_id = workspace
    result = upload(client, case_id, "facture.pdf", make_pdf(["Dossier fictif"]))
    assert result.status_code == expected_status, result.content
    assert result.json()["code"] == expected_code
    assert Document.objects.count() == 0
    root = settings.PRIVATE_STORAGE_ROOT
    assert not all_files(root / "documents")
    assert not all_files(root / "quarantine")


def test_real_clamav_rejects_harmless_eicar_signature(workspace, settings):
    """This is a real scanner integration test: do not mock clamd."""
    client, case_id = workspace
    result = upload(client, case_id, "controle.pdf", EICAR)
    assert result.status_code == 422, result.content
    assert result.json()["code"] == "MALWARE_DETECTED"
    assert Document.objects.count() == 0
    assert not all_files(settings.PRIVATE_STORAGE_ROOT / "documents")
    assert not all_files(settings.PRIVATE_STORAGE_ROOT / "quarantine")


def test_clean_file_passes_scanner_and_keeps_original_bytes(workspace, settings):
    client, case_id = workspace
    original = make_pdf(["Facture commerciale fictive - controle P0"])
    result = upload(client, case_id, "facture.pdf", original)
    assert result.status_code == 201, result.content
    document_id = result.json()["document"]["id"]
    assert Document.objects.get(pk=document_id).sha256
    [path] = all_files(settings.PRIVATE_STORAGE_ROOT / "documents")
    assert path.read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600
    assert not all_files(settings.PRIVATE_STORAGE_ROOT / "quarantine")


def test_application_rejects_mime_spoof_even_after_clean_antivirus(workspace, settings):
    client, case_id = workspace
    result = upload(client, case_id, "facture.pdf", make_png(), content_type="application/pdf")
    assert result.status_code == 422, result.content
    assert result.json()["code"] == "CONTENT_TYPE_MISMATCH"
    assert Document.objects.count() == 0
    assert not all_files(settings.PRIVATE_STORAGE_ROOT / "documents")


def test_organization_isolation_still_applies_after_antivirus(workspace, session):
    client, case_id = workspace
    result = upload(client, case_id, "facture.pdf", make_pdf(["Document privé fictif"]))
    assert result.status_code == 201, result.content
    doc_id = result.json()["document"]["id"]
    other = session("declarant@b.test")
    assert other.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert other.get(f"/api/v1/documents/{doc_id}/download").status_code == 404
    assert other.get(f"/api/v1/documents/{doc_id}/preview").status_code == 404


def test_document_catalog_is_precise_and_legally_non_authoritative(workspace):
    client, _case_id = workspace
    call_command("seed_document_types")
    result = client.get("/api/v1/document-types")
    assert result.status_code == 200, result.content
    types = result.json()["results"]
    codes = {item["code"] for item in types}
    assert {"commercial_invoice", "freight_invoice", "insurance_certificate", "bill_of_lading", "air_waybill"} <= codes
    assert result.json()["version"] == "1.0"
    assert result.json()["families"]["insurance"] == "Assurance"
