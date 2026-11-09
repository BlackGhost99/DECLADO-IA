"""Asynchronous XLSX imports respond immediately and retain owner-only job status."""

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ApiError
from apps.tariffs import async_jobs


@pytest.fixture
def job_env(settings, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = False
    cache.clear()
    monkeypatch.setattr(async_jobs, "_start_thread", lambda *_args: None)
    user = SimpleNamespace(pk=uuid4(), is_authenticated=True, is_reference_manager=True)
    yield user
    cache.clear()


def _fake_xlsx() -> bytes:
    out = BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    return out.getvalue()


@pytest.mark.django_db
def test_returns_queued_job_without_waiting_for_workbook_import(job_env):
    user = job_env
    upload = SimpleUploadedFile("Tarif CEMAC 2022 SWD.xlsx", _fake_xlsx())
    created = async_jobs.queue_import(actor=user, upload=upload, label="CEMAC 2022")
    assert created["state"] == "queued"
    assert async_jobs.job_for_actor(job_id=created["job_id"], actor=user)["state"] == "queued"
    with pytest.raises(ApiError) as error:
        async_jobs.job_for_actor(job_id=created["job_id"], actor=SimpleNamespace(pk=uuid4()))
    assert error.value.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_second_import_rejected_while_first_is_pending(job_env):
    user = job_env
    async_jobs.queue_import(actor=user, upload=SimpleUploadedFile("first.xlsx", _fake_xlsx()), label="CEMAC 2022")
    with pytest.raises(ApiError) as error:
        async_jobs.queue_import(actor=user, upload=SimpleUploadedFile("second.xlsx", _fake_xlsx()), label="CEMAC 2022")
    assert error.value.error_code == "IMPORT_BUSY"


@pytest.mark.django_db
def test_non_manager_cannot_start_unscanned_background_import(job_env):
    no_role = SimpleNamespace(pk=uuid4(), is_authenticated=True, is_reference_manager=False)
    with pytest.raises(ApiError) as error:
        async_jobs.queue_import(actor=no_role, upload=SimpleUploadedFile("test.xlsx", _fake_xlsx()), label="CEMAC")
    assert error.value.error_code == "FORBIDDEN"
