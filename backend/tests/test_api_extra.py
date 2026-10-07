"""Extra coverage for API routers, app.main, app.api package init and app.db.database.

OCR, antivirus, HS classifier, scanners (WIA) and uvicorn are monkeypatched so
every path runs deterministically without Tesseract, Poppler, an antivirus,
scanner hardware or network access. Nothing is written outside ``tmp_path``.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import io
import json
import logging
import os
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api as api_pkg
import app.main as main_mod
from app.api import declaration_auto, exchange_rates, export_sydonia, scanners
from app.api import ocr as ocr_api
from app.core.config import settings
from app.db import database

# ============================================================================
# Shared fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _isolate_app_side_effects(monkeypatch):
    """Keep the app lifespan from touching the repo tree or leaking log handlers."""
    monkeypatch.setattr(main_mod, "configure_hmac_logging", lambda: None)
    monkeypatch.setattr(main_mod, "init_db", lambda: None)
    monkeypatch.setattr(main_mod, "test_db_connection", lambda: True)
    monkeypatch.setattr(settings, "SIGNED_REPOS", [])
    root = logging.getLogger()
    handlers = list(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in handlers:
            root.removeHandler(h)
            h.close()


def _doc(text: str = "", **normalized) -> bytes:
    """Encode a fake document: the fake OCR pipeline reads this JSON back."""
    return json.dumps({"text": text, "normalized": normalized}).encode("utf-8")


class FakePipeline:
    """Stand-in for app.ocr_pipeline.pipeline: decodes the JSON written by _doc()."""

    def __init__(self, decimal_amounts: bool = False, error: Exception | None = None):
        self.calls: list[tuple[str, str]] = []
        self.decimal_amounts = decimal_amounts
        self.error = error

    def run_document(self, path: str, lang: str = "eng+fra") -> dict:
        self.calls.append((path, lang))
        if self.error is not None:
            raise self.error
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        norm = doc["normalized"]
        if self.decimal_amounts and "amounts" in norm:
            norm["amounts"] = [Decimal(str(a)) for a in norm["amounts"]]
        return {
            "source": os.path.basename(path),
            "num_pages": 1,
            "pages": [{"page": 1, "text": doc["text"]}],
            "normalized": norm,
            "cer": None,
            "warnings": [],
        }


class FakeClassifier:
    def __init__(self, result):
        self.result = result
        self.calls: list[str] = []

    def suggest_hs_code(self, text):
        self.calls.append(text)
        return self.result


@pytest.fixture
def decl_env(monkeypatch):
    """Patch AV, OCR and classifier used by declaration_auto."""
    env = types.SimpleNamespace(
        pipeline=FakePipeline(),
        classifier=FakeClassifier({"hs_code": "8517"}),
        av=(True, "clean"),
    )
    monkeypatch.setattr(declaration_auto, "scan_file", lambda path: env.av)
    monkeypatch.setattr(declaration_auto, "ocr_pipeline", env.pipeline)
    monkeypatch.setattr(declaration_auto, "get_classifier_service", lambda: env.classifier)
    return env


# ============================================================================
# /api/declaration/auto
# ============================================================================

AUTO_URL = "/api/declaration/auto"


def test_auto_declaration_full_flow(client, decl_env):
    invoice = _doc(
        "COMMERCIAL INVOICE NO: FAC-2025/01\nIncoterm FOB Shanghai\n"
        "HS 610910 cotton t-shirts\nCountry of Origin: FR\nQty: 5",
        amounts=[100, 1500],
        currencies=["USD"],
    )
    files = {
        "invoice": ("invoice.json", invoice, "application/json"),
        "transport": ("bl.json", _doc("Freight", amounts=[50, 200]), "application/json"),
        "insurance": ("ins.json", _doc("Insurance", amounts=[30]), "application/json"),
    }
    resp = client.post(AUTO_URL, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ci = body["calculation_input"]
    assert ci["invoice_number"] == "FAC-2025/01"
    assert ci["hs_code"] == "610910"
    assert ci["quantity"] == "5"
    assert ci["unit_price"] == "1500"
    assert ci["currency"] == "USD"
    assert ci["incoterm"] == "FOB"
    assert ci["origin_country"] == "FR"
    assert ci["destination_country"] == "CM"
    assert ci["freight_cost"] == "200"
    assert ci["insurance_cost"] == "30"
    assert set(body["extracted"]) == {"invoice", "transport", "insurance"}
    assert body["extracted"]["transport"]["amounts"] == [50, 200]
    assert body["export_hint"]["format"] == "pdf"
    assert body["export_hint"]["calculation"]["freight_cost"] == "200"
    assert body["calculation_result"]
    assert decl_env.classifier.calls == []  # HS found in text, no ML
    assert len(decl_env.pipeline.calls) == 3
    # temp upload copies are removed afterwards
    assert not any(os.path.exists(p) for p, _ in decl_env.pipeline.calls)


def test_auto_declaration_local_path_ml_hs_and_defaults(client, decl_env, tmp_path):
    inv = tmp_path / "invoice.json"
    inv.write_bytes(
        _doc("Ref INV-77 goods (DE) Origin", amounts=[250.5], currencies=[], incoterm="exw")
    )
    resp = client.post(AUTO_URL, data={"invoice_path": str(inv), "destination_country": "ga"})
    assert resp.status_code == 200, resp.text
    ci = resp.json()["calculation_input"]
    assert ci["hs_code"] == "8517"
    assert ci["invoice_number"] == "INV-77"
    assert ci["incoterm"] == "EXW"
    assert ci["origin_country"] == "DE"
    assert ci["destination_country"] == "GA"
    assert ci["currency"] == "EUR"
    assert ci["quantity"] == "1"
    assert ci["freight_cost"] is None and ci["insurance_cost"] is None
    assert decl_env.classifier.calls and decl_env.pipeline.calls[0][0] == str(inv)
    assert inv.exists()  # local files are never deleted


def test_auto_declaration_hs_override_and_origin_override(client, decl_env):
    decl_env.classifier.result = {"hs_code": "unknown"}
    files = {"invoice": ("inv.json", _doc("no code here", amounts=[10]), "application/json")}
    resp = client.post(
        AUTO_URL, files=files, data={"hs_override": "84.71-30", "origin_country": "us"}
    )
    assert resp.status_code == 200, resp.text
    ci = resp.json()["calculation_input"]
    assert ci["hs_code"] == "847130"
    assert ci["origin_country"] == "US"
    assert ci["incoterm"] == "CIF"
    assert ci["invoice_number"] == "INV-AUTO"


@pytest.mark.parametrize("override", [None, "12"])
def test_auto_declaration_hs_not_found(client, decl_env, override):
    decl_env.classifier.result = None
    data = {"hs_override": override} if override else {}
    files = {"invoice": ("inv.json", _doc("plain text", amounts=[10]), "application/json")}
    resp = client.post(AUTO_URL, files=files, data=data)
    assert resp.status_code == 422
    assert "code HS" in resp.json()["detail"]


def test_auto_declaration_missing_total(client, decl_env):
    files = {"invoice": ("inv.json", _doc("HS 610910", amounts=[]), "application/json")}
    resp = client.post(AUTO_URL, files=files)
    assert resp.status_code == 422
    assert "Total" in resp.json()["detail"]


def test_auto_declaration_requires_invoice(client, decl_env):
    resp = client.post(AUTO_URL, data={"origin_country": "CN"})
    assert resp.status_code == 400
    assert "Facture obligatoire" in resp.json()["detail"]


def test_auto_declaration_invoice_path_not_found(client, decl_env, tmp_path):
    resp = client.post(AUTO_URL, data={"invoice_path": str(tmp_path / "missing.pdf")})
    assert resp.status_code == 404
    assert "introuvable" in resp.json()["detail"]


def test_auto_declaration_antivirus_rejects(client, decl_env):
    decl_env.av = (False, "ClamAV: threat found")
    files = {"invoice": ("inv.json", _doc("x", amounts=[1]), "application/json")}
    resp = client.post(AUTO_URL, files=files)
    assert resp.status_code == 400
    assert "Antivirus" in resp.json()["detail"]
    assert decl_env.pipeline.calls == []


def test_auto_declaration_ocr_failure_is_500(client, decl_env):
    decl_env.pipeline.error = RuntimeError("tesseract missing")
    files = {"invoice": ("inv.pdf", b"%PDF-1.4", "application/pdf")}
    resp = client.post(AUTO_URL, files=files)
    assert resp.status_code == 500
    assert "tesseract missing" in resp.json()["detail"]


def test_auto_declaration_decimal_amounts(client, decl_env):
    decl_env.pipeline.decimal_amounts = True
    files = {"invoice": ("inv.json", _doc("HS 610910", amounts=[99.95]), "application/json")}
    resp = client.post(AUTO_URL, files=files)
    assert resp.status_code == 200, resp.text
    assert resp.json()["calculation_input"]["unit_price"] == "99.95"


def test_auto_declaration_unparseable_amount(client, decl_env):
    files = {
        "invoice": ("inv.json", _doc("HS 610910", amounts=[100]), "application/json"),
        "transport": ("t.json", _doc("Freight", amounts=["n/a"]), "application/json"),
    }
    resp = client.post(AUTO_URL, files=files)
    # freight is dropped by _to_decimal, then the response model rejects "n/a"
    assert resp.status_code == 500


def test_auto_declaration_tmp_cleanup_failure_is_ignored(client, decl_env, monkeypatch):
    real_remove = os.remove

    def failing_remove(path):
        raise PermissionError("file locked")

    try:
        with monkeypatch.context() as m:
            m.setattr(declaration_auto.os, "remove", failing_remove)
            files = {"invoice": ("inv.json", _doc("HS 610910", amounts=[5]), "application/json")}
            resp = client.post(AUTO_URL, files=files)
    finally:
        for path, _ in decl_env.pipeline.calls:
            if os.path.exists(path):
                real_remove(path)
    assert resp.status_code == 200, resp.text


def test_run_ocr_from_any_requires_input():
    with pytest.raises(HTTPException) as exc:
        declaration_auto._run_ocr_from_any(None, None, "Transport")
    assert exc.value.status_code == 400
    assert "Transport" in exc.value.detail


def test_save_upload_without_filename():
    upload = UploadFile(file=io.BytesIO(b"abc"), filename=None)
    path = declaration_auto._save_upload_to_tmp(upload)
    try:
        assert Path(path).read_bytes() == b"abc"
        assert Path(path).suffix == ""
    finally:
        os.remove(path)


def test_declaration_text_helpers():
    assert declaration_auto._text_from_ocr_result({}) == ""
    assert declaration_auto._text_from_ocr_result({"pages": [{"text": "a"}, {}]}) == "a\n"
    assert declaration_auto._extract_incoterm("terms: cif douala") == "CIF"
    assert declaration_auto._extract_incoterm("nothing") is None
    assert declaration_auto._extract_invoice_number("Invoice Number: AB-12") == "AB-12"
    assert declaration_auto._extract_invoice_number("ref inv-2024/9") == "inv-2024/9"
    assert declaration_auto._extract_invoice_number("no reference") is None
    assert declaration_auto._extract_origin("Origine: cm") == "CM"
    assert declaration_auto._extract_origin("(IT) Origin") == "IT"
    assert declaration_auto._extract_origin("unknown") is None
    assert declaration_auto._extract_qty("Quantité: 12") == 12
    assert declaration_auto._extract_qty("none") is None


# ============================================================================
# /api/export/sydonia/pdf
# ============================================================================


@pytest.fixture
def sydonia_payload():
    return {
        "numero_declaration": "DCL-2025-0001",
        "date_declaration": "2025-01-15",
        "bureau_douane": "CM-DLA",
        "regime_douanier": "IM4",
        "nom_importateur": "Import SARL",
        "adresse_importateur": "Douala",
        "nif_importateur": "M0123456789",
        "nom_exportateur": "Export Ltd",
        "pays_exportation": "CN",
        "mode_transport": "Maritime",
        "pays_provenance": "CN",
        "pays_origine": "CN",
        "code_sh": "610910",
        "designation": "T-shirts coton",
        "quantite": 100,
        "unite_mesure": "PCE",
        "poids_net": 50.5,
        "poids_brut": 55.0,
        "valeur_cif": 1234567.891,
        "monnaie": "XAF",
        "taux_change": 655.957,
        "droits_douane": 1000,
        "tva": 2000,
        "tci": 10,
        "cci": 20,
        "oad": 5,
        "total_taxes": 3035,
        "valeur_totale": 1237602.89,
        "facture_commerciale": "FAC-1",
        "connaissement": "BL-1",
        "certificat_origine": "CO-1",
    }


def test_export_sydonia_pdf(client, sydonia_payload):
    resp = client.post("/api/export/sydonia/pdf", json=sydonia_payload)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "SYDONIA_610910_2025-01-15.pdf" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


def test_export_sydonia_pdf_without_documents(client, sydonia_payload):
    for key in ("facture_commerciale", "connaissement", "certificat_origine"):
        sydonia_payload[key] = ""
    sydonia_payload["numero_declaration"] = ""
    resp = client.post("/api/export/sydonia/pdf", json=sydonia_payload)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_export_sydonia_pdf_partial_documents(sydonia_payload):
    sydonia_payload["facture_commerciale"] = ""
    sydonia_payload["connaissement"] = ""
    buf = export_sydonia.create_pdf_sydonia(export_sydonia.SydoniaDeclaration(**sydonia_payload))
    assert buf.getvalue().startswith(b"%PDF")


def test_export_sydonia_without_reportlab(client, sydonia_payload, monkeypatch):
    monkeypatch.setattr(export_sydonia, "REPORTLAB_AVAILABLE", False)
    resp = client.post("/api/export/sydonia/pdf", json=sydonia_payload)
    assert resp.status_code == 500
    assert "ReportLab" in resp.json()["detail"]


def test_export_sydonia_validation_error(client):
    resp = client.post("/api/export/sydonia/pdf", json={"code_sh": "6109"})
    assert resp.status_code == 422


def test_format_currency():
    assert export_sydonia.format_currency(1234567.891) == "1 234 567.89"
    assert export_sydonia.format_currency(0) == "0.00"


# ============================================================================
# Scanners (router is not mounted by app.main -> dedicated app)
# ============================================================================


@pytest.fixture
def scanner_client():
    app = FastAPI()
    app.include_router(scanners.router, prefix="/api/scanners")
    with TestClient(app) as c:
        yield c


class _Prop:
    def __init__(self, name, value=None):
        self.Name = name
        self.Value = value


class _Props:
    def __init__(self, props):
        self._props = {p.Name: p for p in props}

    def __call__(self, name):
        return self._props[name]

    def __iter__(self):
        return iter(self._props.values())


class _DeviceInfo:
    def __init__(self, dev_id, dev_type, name, manufacturer=None, connect=None):
        self.DeviceID = dev_id
        self.Type = dev_type
        props = [_Prop("Name", name)]
        if manufacturer:
            props.append(_Prop("Manufacturer", manufacturer))
        self.Properties = _Props(props)
        self._connect = connect

    def Connect(self):
        if isinstance(self._connect, Exception):
            raise self._connect
        return self._connect


def _install_fake_wia(monkeypatch, devices=None, dispatch_error=None):
    def dispatch(prog_id):
        assert prog_id == "WIA.DeviceManager"
        if dispatch_error is not None:
            raise dispatch_error
        infos = types.SimpleNamespace(Count=len(devices), Item=lambda i: devices[i - 1])
        return types.SimpleNamespace(DeviceInfos=infos)

    client_mod = types.ModuleType("win32com.client")
    client_mod.Dispatch = dispatch
    pkg = types.ModuleType("win32com")
    pkg.client = client_mod
    monkeypatch.setitem(sys.modules, "win32com", pkg)
    monkeypatch.setitem(sys.modules, "win32com.client", client_mod)


def test_detect_windows_scanners_with_fake_wia(monkeypatch):
    duplex_device = types.SimpleNamespace(
        Properties=[_Prop("Duplex Enabled"), _Prop("Document Feeder"), _Prop("Brightness")]
    )
    devices = [
        _DeviceInfo("1", 1, "HP ScanJet", "HP", connect=duplex_device),
        _DeviceInfo("2", 2, "Webcam"),  # camera: ignored
        _DeviceInfo("3", 1, "Canon Network MFP", connect=OSError("busy")),
        _DeviceInfo("4", 1, "Basic", "Acme", connect=object()),  # no Properties attr
    ]
    _install_fake_wia(monkeypatch, devices)
    found = scanners.detect_windows_scanners()
    assert [s["id"] for s in found] == ["wia-1", "wia-3", "wia-4"]
    hp, canon, basic = found
    assert hp["name"] == "HP ScanJet (HP)"
    assert hp["status"] == "online" and hp["type"] == "local"
    assert hp["capabilities"] == ["scan", "color", "grayscale", "duplex", "adf"]
    assert canon["name"] == "Canon Network MFP (Inconnu)"
    assert canon["status"] == "offline" and canon["type"] == "network"
    assert basic["capabilities"] == ["scan", "color", "grayscale"]


def test_detect_windows_scanners_without_pywin32(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32com", None)
    monkeypatch.setitem(sys.modules, "win32com.client", None)
    assert scanners.detect_windows_scanners() == []


def test_detect_windows_scanners_wia_error(monkeypatch):
    _install_fake_wia(monkeypatch, dispatch_error=RuntimeError("WIA service stopped"))
    assert scanners.detect_windows_scanners() == []


def test_detect_endpoint_windows(scanner_client, monkeypatch):
    monkeypatch.setattr(scanners.platform, "system", lambda: "Windows")
    _install_fake_wia(monkeypatch, [_DeviceInfo("9", 1, "Epson", "Epson", connect=object())])
    resp = scanner_client.get("/api/scanners/detect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True and body["count"] == 1
    assert body["scanners"][0]["id"] == "wia-9"


@pytest.mark.parametrize("os_name", ["Linux", "Darwin", "Plan9"])
def test_detect_endpoint_defaults(scanner_client, monkeypatch, os_name):
    monkeypatch.setattr(scanners.platform, "system", lambda: os_name)
    resp = scanner_client.get("/api/scanners/detect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["scanners"][0]["id"] == "default-scanner"


def test_detect_endpoint_error(scanner_client, monkeypatch):
    def boom():
        raise RuntimeError("detection crashed")

    monkeypatch.setattr(scanners.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanners, "detect_network_scanners", boom)
    resp = scanner_client.get("/api/scanners/detect")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "detection crashed"


def test_scan_endpoint(scanner_client):
    resp = scanner_client.post(
        "/api/scanners/scan",
        params={"scanner_id": "wia-1", "resolution": 600, "color_mode": "bw", "duplex": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanner_id"] == "wia-1"
    assert body["settings"] == {
        "resolution": 600,
        "color_mode": "bw",
        "format": "pdf",
        "duplex": True,
    }


def test_scan_endpoint_validation_and_error(scanner_client, monkeypatch):
    assert scanner_client.post("/api/scanners/scan").status_code == 422

    class BrokenLogger:
        def info(self, *a, **k):
            raise RuntimeError("logger down")

        def error(self, *a, **k):
            pass

    monkeypatch.setattr(scanners, "logger", BrokenLogger())
    resp = scanner_client.post("/api/scanners/scan", params={"scanner_id": "x"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "logger down"


# ============================================================================
# /api/ocr/*
# ============================================================================


@pytest.fixture
def ocr_env(monkeypatch):
    env = types.SimpleNamespace(pipeline=FakePipeline(), av=(True, "clean"))
    monkeypatch.setattr(ocr_api, "scan_file", lambda path: env.av)
    monkeypatch.setattr(ocr_api, "ocr_pipeline", env.pipeline)
    return env


def test_ocr_demo(client):
    resp = client.post("/api/ocr/demo", json={"text": "Total 1234,56 EUR qty 3"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["word_count"] == 5
    assert body["detected_numbers"] == ["1234,56", "3"]
    assert client.post("/api/ocr/demo", json={"text": ""}).status_code == 422


def test_ocr_process_upload_and_local_path(client, ocr_env, tmp_path):
    files = {"file": ("doc.json", _doc("Facture 42", amounts=[42]), "application/json")}
    resp = client.post("/api/ocr/process", files=files, data={"lang": "fra"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["pages"][0]["text"] == "Facture 42"
    assert ocr_env.pipeline.calls[0][1] == "fra"
    assert not os.path.exists(ocr_env.pipeline.calls[0][0])

    local = tmp_path / "local.json"
    local.write_bytes(_doc("Local doc"))
    resp = client.post("/api/ocr/process", data={"local_path": str(local)})
    assert resp.status_code == 200
    assert resp.json()["normalized"] == {}


def test_ocr_process_input_errors(client, ocr_env, tmp_path):
    assert client.post("/api/ocr/process").status_code == 400
    resp = client.post("/api/ocr/process", data={"local_path": str(tmp_path / "nope.png")})
    assert resp.status_code == 404


def test_ocr_process_antivirus_rejects(client, ocr_env):
    ocr_env.av = (False, "Windows Defender: threat found")
    files = {"file": ("doc.png", b"\x89PNG", "image/png")}
    resp = client.post("/api/ocr/process", files=files)
    assert resp.status_code == 400
    assert "Antivirus" in resp.json()["detail"]


def test_ocr_process_invalid_pdf_returns_empty_result(client, ocr_env, tmp_path):
    ocr_env.pipeline.error = RuntimeError("poppler not installed")
    files = {"file": ("scan.PDF", b"%PDF-1.4", "application/pdf")}
    resp = client.post("/api/ocr/process", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "scan.PDF" and body["num_pages"] == 0 and body["warnings"]

    local = tmp_path / "local.pdf"
    local.write_bytes(b"%PDF-1.4")
    resp = client.post("/api/ocr/process", data={"local_path": str(local)})
    assert resp.status_code == 200
    assert resp.json()["source"] == "local.pdf"


def test_ocr_process_unexpected_error(client, ocr_env):
    ocr_env.pipeline.error = RuntimeError("tesseract not found")
    files = {"file": ("scan.png", b"\x89PNG", "image/png")}
    resp = client.post("/api/ocr/process", files=files)
    assert resp.status_code == 500
    assert "tesseract not found" in resp.json()["detail"]


def test_ocr_process_removes_temp_upload_on_error(client, ocr_env):
    ocr_env.pipeline.error = RuntimeError("boom")
    files = {"file": ("scan.png", b"\x89PNG", "image/png")}
    assert client.post("/api/ocr/process", files=files).status_code == 500
    assert not os.path.exists(ocr_env.pipeline.calls[0][0])


def test_ocr_process_temp_cleanup_failure_is_ignored(client, ocr_env, monkeypatch):
    real_remove = os.remove

    def failing_remove(path):
        raise PermissionError("file locked")

    try:
        with monkeypatch.context() as m:
            m.setattr(ocr_api.os, "remove", failing_remove)
            files = {"file": ("doc.json", _doc("x"), "application/json")}
            resp = client.post("/api/ocr/process", files=files)
    finally:
        for path, _ in ocr_env.pipeline.calls:
            if os.path.exists(path):
                real_remove(path)
    assert resp.status_code == 200


def test_ocr_process_unreadable_upload_filename(ocr_env):
    class BrokenUpload:
        @property
        def filename(self):
            raise RuntimeError("no filename")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(ocr_api.ocr_process(file=BrokenUpload(), local_path=None, lang="eng"))
    assert exc.value.status_code == 500
    assert "no filename" in exc.value.detail


def test_ocr_process_declaration(client, monkeypatch):
    seen = {}

    def fake_extract(stream):
        seen["data"] = stream.read()
        return "DECLARATION\nHS 610910"

    monkeypatch.setattr(ocr_api, "extract_text_from_image", fake_extract)
    monkeypatch.setattr(ocr_api, "parse_declaration", lambda text: {"lines": text.split("\n")})
    files = {"file": ("decl.png", b"img-bytes", "image/png")}
    resp = client.post("/api/ocr/process_declaration", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "decl.png"
    assert body["content_type"] == "image/png"
    assert body["extracted_data"] == {"lines": ["DECLARATION", "HS 610910"]}
    assert seen["data"] == b"img-bytes"


def test_ocr_process_declaration_errors(client, monkeypatch):
    files = {"file": ("decl.pdf", b"%PDF", "application/pdf")}
    resp = client.post("/api/ocr/process_declaration", files=files)
    assert resp.status_code == 400

    monkeypatch.setattr(ocr_api, "extract_text_from_image", lambda s: "Error: no tesseract")
    files = {"file": ("decl.png", b"img", "image/png")}
    resp = client.post("/api/ocr/process_declaration", files=files)
    assert resp.status_code == 500
    assert "Error: no tesseract" in resp.json()["detail"]


# ============================================================================
# /api/exchange-rates
# ============================================================================


def test_exchange_rates_real_config(client):
    resp = client.get("/api/exchange-rates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["XAF"] == 1.0
    assert body["source"] == "CEMAC/BEAC"
    for cur in ("USD", "EUR", "GBP", "CNY"):
        assert body[cur] > 0


def test_exchange_rates_fake_config(client, monkeypatch):
    seen = {}

    class FakeConfig:
        def __init__(self, tariffs_dir):
            seen["dir"] = tariffs_dir

        def get_exchange_rate(self, currency):
            return {"USD": Decimal("600.5"), "EUR": Decimal("655.957")}.get(currency, Decimal("1"))

    monkeypatch.setattr(exchange_rates, "TariffConfig", FakeConfig)
    resp = client.get("/api/exchange-rates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["USD"] == 600.5 and body["EUR"] == 655.957 and body["GBP"] == 1.0
    assert body["last_updated"] is None
    assert seen["dir"].parts[-2:] == ("data", "tariffs")


def test_exchange_rates_error(client, monkeypatch):
    def broken(_dir):
        raise OSError("disk unavailable")

    monkeypatch.setattr(exchange_rates, "TariffConfig", broken)
    resp = client.get("/api/exchange-rates")
    assert resp.status_code == 500
    assert "disk unavailable" in resp.json()["detail"]


# ============================================================================
# app.api package init (optional module loading)
# ============================================================================


def test_api_package_optional_module_fallbacks(monkeypatch):
    """Re-execute app/api/__init__.py in isolation with a broken and a router-less module."""
    no_router = types.ModuleType("app.api.hs_classification")
    monkeypatch.setitem(sys.modules, "app.api.hs_classification", no_router)
    monkeypatch.setitem(sys.modules, "app.api.scanners", None)  # -> ImportError

    pkg_dir = Path(api_pkg.__file__).parent
    spec = importlib.util.spec_from_file_location(
        "app.api", pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)]
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # not registered in sys.modules
    assert module.__all__ == ["api_router"]
    assert sys.modules["app.api"] is api_pkg


# ============================================================================
# app.main
# ============================================================================


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "DECLADO-IA API"
    assert body["endpoints"]["declaration_auto"] == "/api/declaration/auto"


def test_routes_are_mounted_once():
    paths = {getattr(r, "path", "") for r in main_mod.app.routes}
    for expected in (
        "/api/declaration/auto",
        "/api/export/sydonia/pdf",
        "/api/exchange-rates",
        "/api/ocr/process",
    ):
        assert expected in paths
    assert not any(p.startswith("/api/api/") for p in paths)


def _sign_dir(repo: Path, key: str) -> None:
    import hashlib
    import hmac

    from app.security.signatures import compute_dir_digest

    digest = compute_dir_digest(repo)
    mac = hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest()
    (repo / ".sig").write_text(json.dumps({"digest": digest, "hmac": mac}), encoding="utf-8")


def _run_lifespan():
    async def _go():
        async with main_mod.lifespan(main_mod.app):
            pass

    asyncio.run(_go())


def test_lifespan_signed_repos_and_db_status(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "LOG_HMAC_KEY", "lifespan-test-key")
    signed = tmp_path / "models"
    signed.mkdir()
    (signed / "m.bin").write_bytes(b"weights")
    _sign_dir(signed, "lifespan-test-key")
    unsigned = tmp_path / "config"
    unsigned.mkdir()
    signed_file = tmp_path / "rules.yaml"
    signed_file.write_text("a: 1")
    import hashlib
    import hmac

    digest = hashlib.sha256(b"a: 1").hexdigest()
    mac = hmac.new(b"lifespan-test-key", digest.encode(), hashlib.sha256).hexdigest()
    (tmp_path / "rules.yaml.sig").write_text(json.dumps({"digest": digest, "hmac": mac}))
    monkeypatch.setattr(
        settings, "SIGNED_REPOS", [tmp_path / "absent", unsigned, signed, signed_file]
    )
    calls = []
    monkeypatch.setattr(main_mod, "configure_hmac_logging", lambda: calls.append("hmac"))
    monkeypatch.setattr(main_mod, "init_db", lambda: calls.append("init"))
    monkeypatch.setattr(main_mod, "test_db_connection", lambda: False)

    _run_lifespan()
    assert calls == ["hmac", "init"]
    assert (tmp_path / "data").is_dir()


def test_lifespan_invalid_signature_aborts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "LOG_HMAC_KEY", "lifespan-test-key")
    repo = tmp_path / "models"
    repo.mkdir()
    (repo / "m.bin").write_bytes(b"weights")
    _sign_dir(repo, "lifespan-test-key")
    (repo / "m.bin").write_bytes(b"tampered")
    monkeypatch.setattr(settings, "SIGNED_REPOS", [repo])
    with pytest.raises(RuntimeError, match="Invalid signature"):
        _run_lifespan()


def test_lifespan_db_init_error_is_logged(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def broken_init():
        raise RuntimeError("db locked")

    monkeypatch.setattr(main_mod, "init_db", broken_init)
    _run_lifespan()  # error is swallowed and logged


def test_main_module_entrypoint_and_router_failure(monkeypatch):
    """Execute a private copy of app/main.py as __main__ with uvicorn.run stubbed."""
    import uvicorn

    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: runs.append((app, kw)))

    real_import = importlib.import_module
    bogus = types.SimpleNamespace(router="not-a-router")

    def fake_import(name, package=None):
        if name == "app.api.hs_search":
            return bogus  # include_router() will fail on it
        return real_import(name, package)

    # The copy runs app.main's import-time code only; its lifespan is never started.
    spec = importlib.util.spec_from_file_location("__main__", main_mod.__file__)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as m:
        m.setattr(importlib, "import_module", fake_import)
        spec.loader.exec_module(module)

    assert len(runs) == 1
    app_obj, kwargs = runs[0]
    assert app_obj is module.app
    assert kwargs == {
        "host": settings.API_HOST,
        "port": settings.API_PORT,
        "reload": settings.API_RELOAD,
    }
    assert "hs_search" in module._loaded_optional
    assert sys.modules["app.main"] is main_mod


# ============================================================================
# app.db.database
# ============================================================================


class _FakeCursor:
    def __init__(self, cipher_row=("4.5.6",), fail_on=()):
        self.executed = []
        self.cipher_row = cipher_row
        self.fail_on = fail_on
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if any(sql.startswith(prefix) for prefix in self.fail_on):
            raise RuntimeError(f"cannot run {sql}")

    def fetchone(self):
        return self.cipher_row

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


@pytest.mark.parametrize("row", [("4.5.6",), (None,), None])
def test_sqlite_pragma_with_sqlcipher(monkeypatch, row):
    monkeypatch.setattr(database, "SQLCIPHER_AVAILABLE", True)
    monkeypatch.setattr(settings, "DB_PASSPHRASE", "throwaway")
    cur = _FakeCursor(cipher_row=row)
    database._set_sqlite_pragma(_FakeConn(cur), None)
    assert cur.executed[:2] == ["PRAGMA key = ?", "PRAGMA cipher_version;"]
    assert "PRAGMA journal_mode = WAL" in cur.executed
    assert cur.closed


def test_sqlite_pragma_failures_are_tolerated(monkeypatch):
    monkeypatch.setattr(database, "SQLCIPHER_AVAILABLE", True)
    monkeypatch.setattr(settings, "DB_PASSPHRASE", None)
    cur = _FakeCursor(fail_on=("PRAGMA key", "PRAGMA foreign_keys"))
    database._set_sqlite_pragma(_FakeConn(cur), None)
    assert cur.executed == ["PRAGMA key = ?", "PRAGMA foreign_keys = ON"]
    assert cur.closed


def test_sqlite_pragma_without_sqlcipher(monkeypatch):
    monkeypatch.setattr(database, "SQLCIPHER_AVAILABLE", False)
    cur = _FakeCursor()
    database._set_sqlite_pragma(_FakeConn(cur), None)
    assert cur.executed == ["PRAGMA foreign_keys = ON", "PRAGMA journal_mode = WAL"]


@pytest.fixture
def memory_engine(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    yield engine
    engine.dispose()


def test_init_db_and_connection(memory_engine):
    database.init_db()
    from sqlalchemy import inspect

    assert inspect(memory_engine).get_table_names()
    assert database.test_db_connection() is True


def test_init_db_failure(memory_engine, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(database.Base.metadata, "create_all", broken)
    with pytest.raises(RuntimeError, match="disk full"):
        database.init_db()


def test_db_connection_failure(monkeypatch):
    def broken_session():
        raise RuntimeError("cannot open")

    monkeypatch.setattr(database, "SessionLocal", broken_session)
    assert database.test_db_connection() is False


def test_get_db_yields_and_closes(memory_engine):
    gen = database.get_db()
    session = next(gen)
    assert session.bind is memory_engine
    with pytest.raises(StopIteration):
        next(gen)


def _exec_copy(path: str, name: str) -> types.ModuleType:
    """Execute a private copy of an app module (never registered in sys.modules)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_database_module_with_sqlcipher_installed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # the copy's engine never connects, but stay isolated
    fake_pkg = types.ModuleType("pysqlcipher3")
    fake_dbapi = types.ModuleType("pysqlcipher3.dbapi2")
    fake_pkg.dbapi2 = fake_dbapi
    monkeypatch.setitem(sys.modules, "pysqlcipher3", fake_pkg)
    monkeypatch.setitem(sys.modules, "pysqlcipher3.dbapi2", fake_dbapi)
    module = _exec_copy(database.__file__, "database_sqlcipher_copy")
    try:
        assert module.SQLCIPHER_AVAILABLE is True
    finally:
        module.engine.dispose()
    assert module.engine is not database.engine
    assert list(tmp_path.iterdir()) == []


def test_export_sydonia_module_without_reportlab(monkeypatch):
    # a None entry in sys.modules makes the import raise ImportError
    monkeypatch.setitem(sys.modules, "reportlab", None)
    monkeypatch.setitem(sys.modules, "reportlab.lib", None)
    module = _exec_copy(export_sydonia.__file__, "export_sydonia_no_reportlab")
    assert module.REPORTLAB_AVAILABLE is False
    assert export_sydonia.REPORTLAB_AVAILABLE is True
