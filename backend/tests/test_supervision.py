"""Console ClairTransit > Supervision (SUP-01 à SUP-06, T90 à T93)."""

from contextlib import contextmanager

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents import antivirus
from apps.documents.models import Document
from apps.documents.synthetic import make_pdf, make_png
from apps.supervision.models import OperationalEvent
from tests.test_ai_platform import operator  # noqa: F401  (fixture : exploitant avec MFA)

URL = "/api/v1/platform/supervision"


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"


def fake_scanner(monkeypatch, verdict):
    """ClamAV simulé : verdict(données) lève MalwareDetected / ScanUnavailable ou rend None (sain)."""

    class FakeStream:
        def __init__(self):
            self.data = b""

        def feed(self, chunk):
            self.data += chunk

        def verdict(self):
            verdict(self.data)

    @contextmanager
    def open_stream():
        yield FakeStream()

    monkeypatch.setattr(antivirus, "open_stream", open_stream)
    monkeypatch.setattr(antivirus, "version", lambda: "ClamAV 1.5.4/27800/Mon Nov  2 08:00:00 2026")


def clean(_data):
    return None


def upload(client, case_id, name, contents, content_type="application/pdf"):
    file = SimpleUploadedFile(name, contents, content_type=content_type)
    return client.upload(f"/api/v1/cases/{case_id}/documents", {"file": file})


@pytest.fixture
def agent(world, session):
    client = session("declarant@a.test")
    case = client.post("/api/v1/cases", {"title": "Supervision"})
    assert case.status_code == 201
    return client, case.json()["id"]


def test_t90_supervision_is_for_the_platform_operator_only(world, session, settings, operator, monkeypatch):  # noqa: F811
    fake_scanner(monkeypatch, clean)
    settings.AI_PROVIDER, settings.AI_API_KEY = "gemini", "secret-never-shown"
    for email in ("admin@a.test", "declarant@b.test"):
        assert session(email).get(URL).status_code == 403
        assert session(email).post(f"{URL}/antivirus-test").status_code == 403
    resp = operator.get(URL, days=7)
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert set(data) >= {"antivirus", "reading", "ai", "rejections", "incidents", "organizations"}
    assert data["antivirus"]["probe"] == {
        "state": "ok",
        "engine": "ClamAV 1.5.4",
        "signatures": "27800",
        "signatures_date": "Mon Nov  2 08:00:00 2026",
        "response_ms": data["antivirus"]["probe"]["response_ms"],
        "checked_at": data["antivirus"]["probe"]["checked_at"],
    }
    assert data["antivirus"]["mode"] == "fail_closed"
    assert data["ai"]["provider"]["label"] and "secret-never-shown" not in resp.content.decode()
    assert {o["name"] for o in data["organizations"]} == {"Société A", "Société B"}
    assert operator.get(URL, days=3).status_code == 400


def test_t90_antivirus_down_is_shown(world, settings, operator):  # noqa: F811
    settings.CLAMAV_PORT = 1
    probe = operator.get(URL).json()["antivirus"]["probe"]
    assert probe["state"] == "unavailable" and "ClamAV" in probe["message"]


def test_t91_rejected_pieces_are_kept_with_their_reason_but_never_their_name(world, operator, agent, monkeypatch):  # noqa: F811
    client, case_id = agent

    def infected(_data):
        raise antivirus.MalwareDetected("test")

    fake_scanner(monkeypatch, infected)
    refused = upload(client, case_id, "facture-client-secret.pdf", make_pdf(["Dossier fictif"]))
    assert refused.status_code == 422 and refused.json()["code"] == "MALWARE_DETECTED"
    fake_scanner(monkeypatch, clean)
    spoof = upload(client, case_id, "photo-secret.pdf", make_png())
    assert spoof.status_code == 422 and spoof.json()["code"] == "CONTENT_TYPE_MISMATCH"
    assert upload(client, case_id, "bonne.pdf", make_pdf(["Pièce fictive"])).status_code == 201
    assert Document.objects.count() == 1  # les refus n'ont rien laissé, sauf leur note

    # Une seule note par refus : l'erreur générique de la requête ne la répète pas.
    assert OperationalEvent.objects.count() == 2
    data = operator.get(URL).json()
    assert "secret" not in str(data["rejections"])
    by_code = {r["code"]: r for r in data["rejections"]}
    malware = by_code["MALWARE_DETECTED"]
    assert malware["category"] == "antivirus" and malware["organization"] == "Société A"
    assert malware["actor"] == "declarant" and malware["details"]["extension"] == "pdf"
    assert malware["details"]["sha256_prefix"] and malware["details"]["bytes"] > 0
    assert by_code["CONTENT_TYPE_MISMATCH"]["category"] == "document"
    assert by_code["CONTENT_TYPE_MISMATCH"]["message"]
    assert data["antivirus"]["counts"] == {"clean": 1, "malware": 1, "unavailable": 0}
    org_a = next(o for o in data["organizations"] if o["name"] == "Société A")
    assert org_a["rejected_documents"] == 2 and org_a["documents"] == 1 and org_a["cases"] == 1


def test_t92_refused_actions_and_server_errors_show_without_private_data(world, operator, agent, monkeypatch):  # noqa: F811
    client, case_id = agent
    refused = client.patch(f"/api/v1/cases/{case_id}", {"title": "Nouveau", "row_version": 99})
    assert refused.status_code == 409
    assert client.get("/api/v1/cases/00000000-0000-0000-0000-000000000000").status_code == 404  # non noté

    from apps.cases import api as cases_api

    def boom(*args, **kwargs):
        raise RuntimeError("données privées du client")

    monkeypatch.setattr(cases_api.CaseListView, "get", boom)
    with pytest.raises(RuntimeError):
        client.get("/api/v1/cases")
    data = operator.get(URL).json()["incidents"]
    assert data["refused_actions"] == 1 and data["server_errors"] == 1
    server = next(e for e in data["events"] if e["category"] == "server")
    assert server["message"] == "Exception RuntimeError" and server["organization"] == "Société A"
    assert server["details"]["route"] == "api/v1/cases" and server["details"]["http_status"] == 500
    assert "privées" not in str(data)
    conflict = next(e for e in data["events"] if e["category"] == "request")
    assert conflict["details"]["method"] == "PATCH" and conflict["details"]["http_status"] == 409


def test_t93_antivirus_self_test_proves_detection_and_is_logged(world, operator, monkeypatch):  # noqa: F811
    from apps.documents.management.commands.verifier_antivirus import eicar

    def real_like(data):
        if data == eicar():
            raise antivirus.MalwareDetected("Eicar")

    fake_scanner(monkeypatch, real_like)
    result = operator.post(f"{URL}/antivirus-test")
    assert result.status_code == 200 and result.json()["ok"] is True
    assert [s["step"] for s in result.json()["steps"]] == ["eicar", "clean"]
    last = operator.get(URL).json()["antivirus"]["last_test"]
    assert last["code"] == "SELF_TEST_PASSED" and last["actor"]

    fake_scanner(monkeypatch, clean)  # signatures absentes : EICAR passe
    failed = operator.post(f"{URL}/antivirus-test").json()
    assert failed["ok"] is False and failed["steps"][0]["ok"] is False
    assert operator.get(URL).json()["antivirus"]["last_test"]["code"] == "SELF_TEST_FAILED"


def test_t90_ocr_unavailable_says_why_without_paths(world, operator, settings, monkeypatch):  # noqa: F811
    import pytesseract

    def not_found():
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", not_found)
    ocr = operator.get(URL).json()["reading"]["engines"]["ocr"]
    assert ocr["available"] is False and ocr["reason"] == "not_found"

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.5.0")
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["osd", "deu"])
    ocr = operator.get(URL).json()["reading"]["engines"]["ocr"]
    assert ocr["reason"] == "languages_missing" and ocr["languages"] == ["deu"]

    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["osd", "eng", "fra"])
    ocr = operator.get(URL).json()["reading"]["engines"]["ocr"]
    assert ocr == {"available": True, "version": "5.5.0", "languages": ["eng", "fra"], "reason": ""}


def test_ocr_tesseract_cmd_setting_points_pytesseract_to_the_binary(settings, monkeypatch):
    import pytesseract
    from django.apps import apps

    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
    settings.OCR_TESSERACT_CMD = r"C:\ClairTransit\outils\tesseract\tesseract.exe"
    apps.get_app_config("extraction").ready()
    assert pytesseract.pytesseract.tesseract_cmd == settings.OCR_TESSERACT_CMD
