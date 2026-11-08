"""Staging-only antivirus exception for SWD reference workbooks; never in production."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ApiError
from apps.documents import antivirus
from apps.tariffs import uploads


def test_reference_manager_can_stage_xlsx_in_staging_without_clamav(settings, monkeypatch, tmp_path):
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = False
    settings.PRIVATE_STORAGE_ROOT = tmp_path
    monkeypatch.setenv("APP_ENV", "staging")
    actor = SimpleNamespace(is_authenticated=True, is_reference_manager=True)
    monkeypatch.setattr(uploads.recorder, "note", lambda **_kwargs: None)
    monkeypatch.setattr(
        antivirus, "open_stream",
        lambda: (_ for _ in ()).throw(AssertionError("ClamAV must not be called")),
    )
    staged = uploads._stage(SimpleUploadedFile("tarif.xlsx", b"synthetic-test"), actor=actor, kind="xlsx")
    assert staged.path.read_bytes() == b"synthetic-test"
    staged.path.unlink()


def test_non_manager_and_non_staging_still_require_scanning(settings, monkeypatch, tmp_path):
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = False
    settings.PRIVATE_STORAGE_ROOT = tmp_path
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setattr(uploads.recorder, "note", lambda **_kwargs: None)
    manager = SimpleNamespace(is_authenticated=True, is_reference_manager=True)
    non_manager = SimpleNamespace(is_authenticated=True, is_reference_manager=False)
    monkeypatch.setattr(antivirus, "open_stream", lambda: (_ for _ in ()).throw(antivirus.ScanUnavailable("offline")))
    for actor, kind in [(non_manager, "xlsx"), (manager, "csv")]:
        with pytest.raises(ApiError) as error:
            uploads._stage(SimpleUploadedFile("tarif." + kind, b"sample"), actor=actor, kind=kind)
        assert error.value.error_code == "SCAN_UNAVAILABLE"
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ApiError) as error:
        uploads._stage(SimpleUploadedFile("tarif.xlsx", b"sample"), actor=manager, kind="xlsx")
    assert error.value.error_code == "SCAN_UNAVAILABLE"


def test_staging_tariff_bypass_is_limited_in_size(settings, monkeypatch, tmp_path):
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = False
    settings.PRIVATE_STORAGE_ROOT = tmp_path
    monkeypatch.setenv("APP_ENV", "staging")
    actor = SimpleNamespace(is_authenticated=True, is_reference_manager=True)
    monkeypatch.setattr(uploads.recorder, "note", lambda **_kwargs: None)
    monkeypatch.setattr(uploads, "STAGING_UNSCANNED_TARIFF_MAX_BYTES", 5)
    with pytest.raises(ApiError) as error:
        uploads._stage(SimpleUploadedFile("tarif.xlsx", b"over-limit"), actor=actor, kind="xlsx")
    assert error.value.error_code == "FILE_TOO_LARGE"
    assert not list((Path(tmp_path) / "quarantine").glob("*"))


def test_debug_mode_never_exempts_reference_manager(settings, monkeypatch):
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = True
    monkeypatch.setenv("APP_ENV", "staging")
    actor = SimpleNamespace(is_authenticated=True, is_reference_manager=True)
    assert not uploads.staging_tariff_bypass(actor=actor, kind="xlsx")
