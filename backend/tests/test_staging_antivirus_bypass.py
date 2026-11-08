"""Temporary staging-only AV bypass: fake organizations only, clearly unscanned and size-capped."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.core.exceptions import ApiError
from apps.documents import antivirus
from apps.documents.services import store_upload
from apps.documents.synthetic import make_pdf, make_png
from apps.supervision.models import OperationalEvent


@pytest.fixture
def demo_world(world, settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_UNSCANNED_MAX_BYTES = 10 * 1024 * 1024
    settings.DEBUG = False
    org = world["org_a"]
    org.is_demo = True
    org.save(update_fields=["is_demo"])
    return org, world["users"]["a_declarant"]


@pytest.mark.django_db
def test_demo_upload_succeeds_without_scanner_but_never_claims_clamav_clean(demo_world, monkeypatch):
    org, user = demo_world

    def no_scanner():
        raise AssertionError("ClamAV must not be contacted for a fake staging organization")

    monkeypatch.setattr(antivirus, "open_stream", no_scanner)
    data = make_pdf(["Facture fictive DECLADO IA - 2026"])
    document = store_upload(
        organization=org,
        actor=user,
        upload=SimpleUploadedFile("facture-fictive.pdf", data, content_type="application/pdf"),
    )
    assert document.mime == "application/pdf"
    assert AuditEvent.objects.filter(
        event_type="document.stored",
        organization=org,
        current__antivirus="not_scanned_staging",
    ).exists()
    assert OperationalEvent.objects.filter(
        category=OperationalEvent.Category.ANTIVIRUS,
        organization=org,
        code="STAGING_SCAN_BYPASSED",
    ).exists()


@pytest.mark.django_db
def test_non_demo_organization_remains_fail_closed(demo_world, world, monkeypatch):
    _org, _user = demo_world

    def unavailable():
        raise antivirus.ScanUnavailable("scanner absent")

    monkeypatch.setattr(antivirus, "open_stream", unavailable)
    with pytest.raises(ApiError) as error:
        store_upload(
            organization=world["org_b"],
            actor=world["users"]["b_admin"],
            upload=SimpleUploadedFile("facture.pdf", make_pdf(["Fictif"]), content_type="application/pdf"),
        )
    assert error.value.code == "MALWARE_SCAN_UNAVAILABLE"


@pytest.mark.django_db
def test_demo_bypass_cannot_be_used_in_debug(demo_world, settings, monkeypatch):
    org, user = demo_world
    settings.DEBUG = True
    monkeypatch.setattr(
        antivirus,
        "open_stream",
        lambda: (_ for _ in ()).throw(antivirus.ScanUnavailable("scanner absent")),
    )
    with pytest.raises(ApiError) as error:
        store_upload(
            organization=org,
            actor=user,
            upload=SimpleUploadedFile("facture.pdf", make_pdf(["Fictif"]), content_type="application/pdf"),
        )
    assert error.value.code == "MALWARE_SCAN_UNAVAILABLE"


@pytest.mark.django_db
def test_demo_bypass_keeps_size_cap_and_mime_checks(demo_world, settings):
    org, user = demo_world
    settings.STAGING_UNSCANNED_MAX_BYTES = 80
    with pytest.raises(ApiError) as error:
        store_upload(
            organization=org,
            actor=user,
            upload=SimpleUploadedFile("facture.pdf", b"x" * 81, content_type="application/pdf"),
        )
    assert error.value.code == "FILE_TOO_LARGE"

    settings.STAGING_UNSCANNED_MAX_BYTES = 10 * 1024 * 1024
    with pytest.raises(ApiError) as error:
        store_upload(
            organization=org,
            actor=user,
            upload=SimpleUploadedFile("facture.pdf", make_png(), content_type="application/pdf"),
        )
    assert error.value.code == "CONTENT_TYPE_MISMATCH"


@pytest.mark.django_db
def test_demo_supervision_shows_real_scanner_state_and_bypass(demo_world):
    from apps.supervision.services import runtime_section

    runtime = runtime_section(
        {"probe": {"state": "unavailable"}},
        {"engines": {"ocr": {"available": False, "languages": []}}},
        {"provider": {"configured": False}},
        {"execution": "inline", "outbox_pending": 0, "outbox_stale": 0},
    )
    assert runtime["clamav"]["state"] == "demo_bypass"
    assert runtime["clamav"]["scanner_state"] == "unavailable"
    assert runtime["clamav"]["demo_bypass"]
    assert not runtime["clamav"]["blocking_uploads"]
