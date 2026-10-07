"""Extra coverage for app.ocr_pipeline.

Every test is hermetic: Tesseract and Poppler are never invoked (CI runs on
windows-latest without them). The pytesseract / pdf2image entry points are
monkeypatched so the application code paths still execute. PDFs are built with
reportlab and images with PIL, in tmp_path.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import runpy
import sys
import types

import numpy as np
import pytesseract
import pytest
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ocr_pipeline import cli as ocr_cli
from app.ocr_pipeline import eval as ocr_eval
from app.ocr_pipeline import (
    normalize,
    ocr_engine,
    parser,
    pdf_utils,
    pipeline,
    preprocessing,
    processor,
    table_extraction,
)
from app.ocr_pipeline.types import BBox, DocumentResult, NormalizedFields, PageResult, Word

TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext"
)


def _tsv(*rows: str) -> str:
    return "\n".join([TSV_HEADER, *rows]) + "\n"


TSV_SAMPLE = _tsv(
    "5\t1\t1\t1\t1\t1\t10\t20\t30\t40\t95.5\tInvoice",
    "5\t1\t1\t1\t1\t2\t50\t20\t30\t40\t-1\t45.67",
    "5\t1\t1\t1\t1\t3\t90\t20\t30\t40\t88\tUSD",
)


@pytest.fixture(autouse=True)
def _restore_tesseract_cmd(monkeypatch):
    """processor.py overwrites the global tesseract_cmd; restore it after each test."""
    monkeypatch.setattr(
        pytesseract.pytesseract, "tesseract_cmd", pytesseract.pytesseract.tesseract_cmd
    )


@pytest.fixture
def no_tesseract(monkeypatch):
    """Make any accidental call to the real tesseract binary fail loudly."""

    def _boom(*_a, **_k):
        raise AssertionError("real tesseract must not be called in tests")

    monkeypatch.setattr(pytesseract, "image_to_data", _boom)
    monkeypatch.setattr(pytesseract, "image_to_string", _boom)


def _make_pdf(path, pages):
    """Write a PDF. Each page is a list of text lines; an empty list is a blank page."""
    c = canvas.Canvas(str(path), pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        if lines:
            # A 2x2 ruled grid so pdfplumber detects a table.
            xs, ys = [72, 200, 330], [600, 630, 660]
            c.grid(xs, ys)
            c.drawString(80, 640, "HS")
            c.drawString(210, 640, "Qty")
            c.drawString(80, 610, "8471")
            c.drawString(210, 610, "2")
        c.showPage()
    c.save()
    return path


def _make_png(path, size=(120, 60)):
    img = Image.new("RGB", size, color=(255, 255, 255))
    ImageDraw.Draw(img).rectangle([10, 10, 100, 40], outline=(0, 0, 0))
    img.save(path)
    return path


def _png_bytes(size=(64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_dates_both_formats_dedup_and_invalid(self):
        text = "Le 12/01/2024, puis 2024-03-05 et 12.01.2024; invalide 31/02/2024"
        assert normalize.normalize_date(text) == ["2024-01-12", "2024-03-05"]

    def test_amounts_dedup_and_unparseable(self):
        text = "Total 1 500,50 puis 1500.50 et 12,34 et 1,234,567"
        amts = normalize.normalize_amounts(text)
        assert 1500.5 in amts
        assert 12.34 in amts
        assert amts.count(1500.5) == 1
        # "1,234,567" -> "1.234.567" cannot be parsed and is dropped
        assert all(a != 1234567 for a in amts)

    def test_to_float_failure_returns_none(self):
        assert normalize._to_float("1.2.3") is None
        assert normalize._to_float("1 000,25") == 1000.25

    def test_currencies_symbols_and_cemac_mapping(self):
        text = "Montant 100 € soit 120 $ ou 65 000 FCFA, 10 cfa, 3 XOF, 2 eur"
        assert normalize.normalize_currencies(text) == ["EUR", "USD", "XAF", "XOF"]

    def test_empty_text(self):
        assert normalize.normalize_date("") == []
        assert normalize.normalize_amounts("") == []
        assert normalize.normalize_currencies("") == []


# ---------------------------------------------------------------------------
# ocr_engine
# ---------------------------------------------------------------------------


class TestOcrEngine:
    def test_parse_empty(self):
        assert ocr_engine._parse_tesseract_data("") == ("", [])
        assert ocr_engine._parse_tesseract_data("   \n  ") == ("", [])

    def test_parse_words_and_conf(self):
        text, words = ocr_engine._parse_tesseract_data(TSV_SAMPLE)
        assert text == "Invoice 45.67 USD"
        assert [w.text for w in words] == ["Invoice", "45.67", "USD"]
        assert words[0].bbox == BBox(10, 20, 30, 40)
        assert words[0].conf == 95.5
        assert words[1].conf is None  # conf == -1

    def test_parse_skips_bad_rows_and_handles_bad_numbers(self):
        data = _tsv(
            "5\t1\t1\t1\t1\t1\t10\t20",  # wrong column count
            "5\t1\t1\t1\t1\t2\t10\t20\t30\t40\t90\t   ",  # empty text
            "5\t1\t1\t1\t1\t3\tx\t20\t30\t40\t90\tBad",  # non-numeric bbox
        )
        text, words = ocr_engine._parse_tesseract_data(data)
        assert text == "Bad"
        assert words == [Word(text="Bad", bbox=BBox(0, 0, 0, 0), conf=None)]

    def test_ocr_image_success(self, monkeypatch):
        calls = {}

        def fake_image_to_data(img, lang, config, output_type):
            calls.update(lang=lang, config=config, output_type=output_type)
            return TSV_SAMPLE

        monkeypatch.setattr(ocr_engine.pytesseract, "image_to_data", fake_image_to_data)
        text, words = ocr_engine.ocr_image(np.zeros((10, 10), dtype=np.uint8), lang="fra")
        assert text == "Invoice 45.67 USD"
        assert len(words) == 3
        assert calls["lang"] == "fra"
        assert "--psm 6" in calls["config"]
        assert calls["output_type"] == pytesseract.Output.STRING

    def test_ocr_image_tesseract_not_found(self, monkeypatch):
        def raise_nf(*_a, **_k):
            raise pytesseract.TesseractNotFoundError()

        monkeypatch.setattr(ocr_engine.pytesseract, "image_to_data", raise_nf)
        text, words = ocr_engine.ocr_image(np.zeros((5, 5), dtype=np.uint8))
        assert "Tesseract OCR n'est pas installé" in text
        assert words == []

    def test_ocr_image_other_error(self, monkeypatch):
        def raise_rt(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(ocr_engine.pytesseract, "image_to_data", raise_rt)
        assert ocr_engine.ocr_image(np.zeros((5, 5), dtype=np.uint8)) == ("Erreur OCR: boom", [])

    def test_windows_tesseract_autodetection_on_import(self, monkeypatch, tmp_path):
        """Reload the module pretending the first Windows install path exists."""
        tess = ocr_engine.TESSERACT_PATHS[0]
        tessdata = os.path.join(os.path.dirname(tess), "tessdata")
        real_exists = os.path.exists

        def fake_exists(p):
            return p in (tess, tessdata) or real_exists(p)

        # setenv first so undo() also removes a value the reload adds when the
        # variable was originally absent (delenv alone records nothing then).
        monkeypatch.setenv("TESSDATA_PREFIX", "")
        monkeypatch.delenv("TESSDATA_PREFIX")
        monkeypatch.setattr(os.path, "exists", fake_exists)
        try:
            importlib.reload(ocr_engine)
            assert pytesseract.pytesseract.tesseract_cmd == tess
            assert os.environ["TESSDATA_PREFIX"] == tessdata
        finally:
            monkeypatch.undo()
            importlib.reload(ocr_engine)
        assert "TESSDATA_PREFIX" not in os.environ or os.environ["TESSDATA_PREFIX"] != tessdata


# ---------------------------------------------------------------------------
# pdf_utils
# ---------------------------------------------------------------------------


def _fake_os(environ, existing=(), listdirs=None, listdir_error=False):
    """A minimal stand-in for the ``os`` module as used by _find_poppler_bin."""
    existing = set(existing)
    listdirs = listdirs or {}

    def exists(p):
        if p == "RAISE\\pdfinfo.exe" or p == "RAISE/pdfinfo.exe":
            raise OSError("bad entry")
        return p in existing

    def listdir(p):
        if listdir_error:
            raise PermissionError(p)
        return listdirs.get(p, [])

    return types.SimpleNamespace(
        environ=environ,
        pathsep=";",
        listdir=listdir,
        path=types.SimpleNamespace(join=lambda *a: "\\".join(a), exists=exists),
    )


class TestPdfUtils:
    def test_poppler_from_env_var(self, monkeypatch):
        fake = _fake_os({"POPPLER_PATH": "C:\\pop"}, existing={"C:\\pop\\pdfinfo.exe"})
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() == "C:\\pop"

    def test_poppler_from_path_entries(self, monkeypatch):
        fake = _fake_os(
            {"POPPLER_BIN": "C:\\missing", "PATH": ";RAISE;C:\\other;C:\\bin"},
            existing={"C:\\bin\\pdfinfo.exe"},
        )
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() == "C:\\bin"

    def test_poppler_from_common_candidates(self, monkeypatch):
        cand = r"C:\\Program Files\\poppler\\bin"
        fake = _fake_os({"PATH": ""}, existing={cand + "\\pdfinfo.exe"})
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() == cand

    def test_poppler_from_program_files_scan(self, monkeypatch):
        root = r"C:\\Program Files (x86)"
        found = "\\".join([root, "Poppler-24", "bin"])
        fake = _fake_os(
            {},
            existing={root, found + "\\pdfinfo.exe"},
            listdirs={root: ["Other", "Poppler-24"]},
        )
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() == found

    def test_poppler_scan_finds_nothing(self, monkeypatch):
        root = r"C:\\Program Files"
        fake = _fake_os({}, existing={root}, listdirs={root: ["poppler-broken"]})
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() is None

    def test_poppler_scan_error_is_swallowed(self, monkeypatch):
        fake = _fake_os({}, existing={r"C:\\Program Files"}, listdir_error=True)
        monkeypatch.setattr(pdf_utils, "os", fake)
        assert pdf_utils._find_poppler_bin() is None

    def test_require_helpers(self, monkeypatch):
        pdf_utils._require_pdfplumber()
        pdf_utils._require_pdf2image()
        monkeypatch.setattr(pdf_utils, "pdfplumber", None)
        monkeypatch.setattr(pdf_utils, "convert_from_path", None)
        with pytest.raises(RuntimeError, match="pdfplumber"):
            pdf_utils._require_pdfplumber()
        with pytest.raises(RuntimeError, match="pdf2image"):
            pdf_utils._require_pdf2image()
        with pytest.raises(RuntimeError):
            list(pdf_utils.iter_pdf_pages_as_images("x.pdf"))

    @pytest.mark.parametrize("poppler", ["C:\\poppler\\bin", None])
    def test_iter_pdf_pages_as_images(self, monkeypatch, poppler):
        calls = []
        imgs = [Image.new("RGB", (4, 4)), Image.new("RGB", (4, 4))]

        def fake_convert(path, **kwargs):
            calls.append((path, kwargs))
            return imgs

        monkeypatch.setattr(pdf_utils, "convert_from_path", fake_convert)
        monkeypatch.setattr(pdf_utils, "_find_poppler_bin", lambda: poppler)
        out = list(pdf_utils.iter_pdf_pages_as_images("doc.pdf", dpi=150))
        assert [i for i, _ in out] == [0, 1]
        assert out[1][1] is imgs[1]
        expected = {"dpi": 150}
        if poppler:
            expected["poppler_path"] = poppler
        assert calls == [("doc.pdf", expected)]

    def test_extract_pdf_text_and_tables(self, tmp_path):
        pdf = _make_pdf(tmp_path / "digital.pdf", [["Facture FAC-001", "Total 1500.50 EUR"], []])
        pages = list(pdf_utils.extract_pdf_text_and_tables(str(pdf)))
        assert [p[0] for p in pages] == [0, 1]
        assert "Total 1500.50 EUR" in pages[0][1]
        assert pages[0][2] and pages[0][2][0][0] == ["HS", "Qty"]
        assert pages[1][1] == "" and pages[1][2] == []


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def _gray(img):
    return img if img.ndim == 2 else img[..., 0].copy()


@pytest.fixture
def fast_pipeline(monkeypatch, no_tesseract):
    """Mock OCR (and the slow denoising chain) inside pipeline."""
    monkeypatch.setattr(pipeline, "preprocess_for_ocr", _gray)
    monkeypatch.setattr(
        pipeline,
        "ocr_image",
        lambda img, lang="eng+fra": ("Facture 12/01/2024 total 45.67 USD", [Word("45.67")]),
    )


class TestPipeline:
    def test_require_cv2_missing(self, monkeypatch):
        monkeypatch.setattr(pipeline, "cv2", None)
        with pytest.raises(RuntimeError, match="OpenCV"):
            pipeline._pil_to_cv(Image.new("RGB", (2, 2)))

    def test_pil_to_cv_swaps_channels(self):
        out = pipeline._pil_to_cv(Image.new("RGB", (2, 2), color=(255, 0, 0)))
        assert out.shape == (2, 2, 3)
        assert tuple(out[0, 0]) == (0, 0, 255)

    def test_compute_cer(self):
        assert pipeline._compute_cer("abc", "") == 0.0
        assert pipeline._compute_cer("abc", "abc") == 0.0
        assert pipeline._compute_cer("abd", "abc") == pytest.approx(1 / 3)
        assert pipeline._compute_cer("", "ab") == 1.0

    def test_run_document_image_with_ground_truth(self, tmp_path, fast_pipeline):
        img = _make_png(tmp_path / "scan.png")
        (tmp_path / "scan.gt.txt").write_text(
            "Facture 12/01/2024 total 45.67 USD\n", encoding="utf-8"
        )
        res = pipeline.run_document(str(img), lang="eng")
        assert res["source"] == str(img)
        assert res["num_pages"] == 1
        page = res["pages"][0]
        assert (page["width"], page["height"]) == (120, 60)
        assert page["words"] == [{"text": "45.67", "bbox": None, "conf": None}]
        assert isinstance(page["tables"], list)
        assert res["normalized"]["dates"] == ["2024-01-12"]
        assert 45.67 in res["normalized"]["amounts"]
        assert res["normalized"]["currencies"] == ["USD"]
        assert res["cer"] == 0.0
        assert res["warnings"] == []

    def test_run_document_digital_pdf(self, tmp_path, monkeypatch, no_tesseract):
        def no_raster(*_a, **_k):
            raise AssertionError("digital pages must not be rasterised")

        monkeypatch.setattr(pipeline, "iter_pdf_pages_as_images", no_raster)
        pdf = _make_pdf(tmp_path / "digital.pdf", [["Facture du 05/03/2024", "Total 99.90 EUR"]])
        res = pipeline.run_document(str(pdf))
        assert res["num_pages"] == 1
        assert res["cer"] is None
        page = res["pages"][0]
        assert page["width"] == 0 and page["words"] == []
        assert page["tables"][0]["rows"][0] == ["HS", "Qty"]
        assert res["normalized"]["dates"] == ["2024-03-05"]
        assert res["normalized"]["currencies"] == ["EUR"]

    def test_run_document_scanned_pdf_uses_ocr(self, tmp_path, monkeypatch, fast_pipeline):
        pdf = _make_pdf(tmp_path / "scanned.pdf", [[]])
        raster = Image.new("RGB", (80, 40), color=(255, 255, 255))
        monkeypatch.setattr(pipeline, "iter_pdf_pages_as_images", lambda p: iter([(0, raster)]))
        res = pipeline.run_document(str(pdf))
        assert res["num_pages"] == 1
        assert res["pages"][0]["text"].startswith("Facture")
        assert (res["pages"][0]["width"], res["pages"][0]["height"]) == (80, 40)
        assert res["warnings"] == []

    def test_run_document_scanned_pdf_without_poppler(self, tmp_path, monkeypatch, no_tesseract):
        pdf = _make_pdf(tmp_path / "scanned.pdf", [[]])

        def raise_poppler(_p):
            raise RuntimeError("Unable to get page count. Is poppler installed?")
            yield  # pragma: no cover - make this a generator

        monkeypatch.setattr(pipeline, "iter_pdf_pages_as_images", raise_poppler)
        res = pipeline.run_document(str(pdf))
        assert res["num_pages"] == 1
        assert res["pages"][0]["text"] == ""
        assert len(res["warnings"]) == 2
        assert "poppler" in res["warnings"][0]
        assert "Installez Poppler" in res["warnings"][1]

    def test_run_batch_writes_json(self, tmp_path, fast_pipeline):
        src = tmp_path / "in"
        (src / "sub").mkdir(parents=True)
        _make_png(src / "a.png")
        _make_png(src / "sub" / "b.JPG")
        (src / "notes.txt").write_text("ignored", encoding="utf-8")
        out_dir = tmp_path / "out"
        outs = pipeline.run_batch(str(src), str(out_dir), lang="fra")
        assert sorted(os.path.basename(o) for o in outs) == ["a.json", "b.json"]
        data = json.loads((out_dir / "a.json").read_text(encoding="utf-8"))
        assert data["num_pages"] == 1
        assert data["normalized"]["currencies"] == ["USD"]


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


class TestCli:
    def test_main_calls_run_batch(self, monkeypatch, capsys, tmp_path):
        seen = {}

        def fake_run_batch(input_dir, output_dir, lang):
            seen.update(input_dir=input_dir, output_dir=output_dir, lang=lang)
            return ["x.json", "y.json"]

        monkeypatch.setattr(ocr_cli, "run_batch", fake_run_batch)
        monkeypatch.setattr(sys, "argv", ["ocr", "in_dir", str(tmp_path), "--lang", "fra"])
        ocr_cli.main()
        assert seen == {"input_dir": "in_dir", "output_dir": str(tmp_path), "lang": "fra"}
        assert f"Wrote 2 outputs to {tmp_path}" in capsys.readouterr().out

    def test_main_default_lang(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            ocr_cli, "run_batch", lambda i, o, lang: seen.setdefault("lang", lang) and []
        )
        monkeypatch.setattr(sys, "argv", ["ocr", "in", "out"])
        ocr_cli.main()
        assert seen["lang"] == "eng+fra"

    def test_main_missing_args_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ocr"])
        with pytest.raises(SystemExit) as exc:
            ocr_cli.main()
        assert exc.value.code == 2

    def test_module_entrypoint(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(pipeline, "run_batch", lambda i, o, lang: [])
        monkeypatch.setattr(sys, "argv", ["ocr", "in", str(tmp_path)])
        monkeypatch.delitem(sys.modules, "app.ocr_pipeline.cli")
        runpy.run_module("app.ocr_pipeline.cli", run_name="__main__")
        assert "Wrote 0 outputs" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------


def _write_output(path, *texts):
    path.write_text(json.dumps({"pages": [{"text": t} for t in texts]}), encoding="utf-8")


@pytest.fixture
def eval_tree(tmp_path, monkeypatch):
    """outputs/ next to ground truths; cwd isolated so data/raw is controlled."""
    monkeypatch.chdir(tmp_path)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    # exact match, ground truth sibling of outputs/
    _write_output(outputs / "a.json", "hello", "world")
    (tmp_path / "a.gt.txt").write_text("hello\nworld\n", encoding="utf-8")
    # one substitution out of 4 chars, ground truth in data/raw
    _write_output(outputs / "b.json", "abcd")
    (raw / "b.gt.txt").write_text("abce", encoding="utf-8")
    # empty ground truth -> skipped
    _write_output(outputs / "c.json", "x")
    (tmp_path / "c.gt.txt").write_text("   ", encoding="utf-8")
    # no ground truth -> skipped
    _write_output(outputs / "d.json", "y")
    # non-json -> ignored
    (outputs / "readme.txt").write_text("ignore", encoding="utf-8")
    return outputs


class TestEval:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("", "", 0),
            ("same", "same", 0),
            ("", "abc", 3),
            ("abc", "", 3),
            ("kitten", "sitting", 3),
            ("flaw", "lawn", 2),
        ],
    )
    def test_levenshtein(self, a, b, expected):
        assert ocr_eval._levenshtein(a, b) == expected

    def test_compute_cer_from_outputs(self, eval_tree):
        n, vals = ocr_eval.compute_cer_from_outputs(str(eval_tree))
        assert n == 2
        assert sorted(vals) == [0.0, 0.25]

    def test_main_usage(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["eval"])
        with pytest.raises(SystemExit) as exc:
            ocr_eval.main()
        assert exc.value.code == 2
        assert "Usage" in capsys.readouterr().out

    def test_main_writes_metrics(self, monkeypatch, capsys, eval_tree, tmp_path):
        metrics = tmp_path / "metrics" / "ocr.json"
        monkeypatch.setattr(sys, "argv", ["eval", str(eval_tree), str(metrics)])
        ocr_eval.main()
        out = json.loads(metrics.read_text(encoding="utf-8"))
        assert out["num_samples"] == 2
        assert out["cer_mean"] == pytest.approx(0.125)
        assert out["cer_median"] == 0.25
        assert '"num_samples": 2' in capsys.readouterr().out

    def test_main_no_samples(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        empty = tmp_path / "empty"
        empty.mkdir()
        metrics = tmp_path / "m.json"
        monkeypatch.setattr(sys, "argv", ["eval", str(empty), str(metrics)])
        ocr_eval.main()
        out = json.loads(metrics.read_text(encoding="utf-8"))
        assert out["num_samples"] == 0
        assert out["cer_mean"] is None and out["cer_median"] is None

    def test_module_entrypoint(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["eval"])
        monkeypatch.delitem(sys.modules, "app.ocr_pipeline.eval")
        with pytest.raises(SystemExit):
            runpy.run_module("app.ocr_pipeline.eval", run_name="__main__")


# ---------------------------------------------------------------------------
# processor
# ---------------------------------------------------------------------------


class TestProcessor:
    def test_preprocess_image_for_ocr(self):
        out = processor.preprocess_image_for_ocr(io.BytesIO(_png_bytes((64, 32))))
        assert out.shape == (32, 64)
        assert out.dtype == np.uint8
        assert set(np.unique(out)) <= {0, 255}

    def test_extract_text_from_image(self, monkeypatch):
        seen = {}

        def fake_to_string(img, config):
            seen.update(shape=img.shape, config=config)
            return "DECLARATION OW110"

        monkeypatch.setattr(processor.pytesseract, "image_to_string", fake_to_string)
        text = processor.extract_text_from_image(io.BytesIO(_png_bytes()))
        assert text == "DECLARATION OW110"
        assert seen["shape"] == (32, 64)
        assert "-l fra" in seen["config"]

    def test_extract_text_from_image_error_tesseract_present(self, monkeypatch, capsys):
        monkeypatch.setattr(processor.pytesseract, "get_tesseract_version", lambda: "5.3.0")
        text = processor.extract_text_from_image(io.BytesIO(b"not an image"))
        assert text.startswith("Error processing image:")
        assert "Tesseract version 5.3.0" in capsys.readouterr().out

    def test_extract_text_from_image_error_tesseract_missing(self, monkeypatch, capsys):
        def raise_nf():
            raise pytesseract.TesseractNotFoundError()

        def raise_nf_ocr(*_a, **_k):
            raise pytesseract.TesseractNotFoundError()

        monkeypatch.setattr(processor.pytesseract, "image_to_string", raise_nf_ocr)
        monkeypatch.setattr(processor.pytesseract, "get_tesseract_version", raise_nf)
        text = processor.extract_text_from_image(io.BytesIO(_png_bytes()))
        assert text == "Error: Tesseract is not installed or configured."
        assert "not installed" in capsys.readouterr().out

    def test_extract_text_from_pdf(self, monkeypatch, capsys):
        pages = [Image.new("RGB", (40, 20), "white"), Image.new("RGB", (40, 20), "white")]
        monkeypatch.setattr(processor, "convert_from_path", lambda path, dpi: pages)
        texts = iter(["page one", "page two"])
        monkeypatch.setattr(
            processor.pytesseract, "image_to_string", lambda img, config: next(texts)
        )
        out = processor.extract_text_from_pdf("doc.pdf")
        assert out == "=== PAGE 1 ===\npage one\n\n=== PAGE 2 ===\npage two"
        assert "Processing page 2/2" in capsys.readouterr().out

    def test_extract_text_from_pdf_error(self, monkeypatch):
        def raise_poppler(path, dpi):
            raise RuntimeError("poppler missing")

        monkeypatch.setattr(processor, "convert_from_path", raise_poppler)
        assert processor.extract_text_from_pdf("doc.pdf") == "Error: poppler missing"


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

DECLARATION_TEXT = """DECLARATION: OW110
B.DOUALA PORT
Expediteur
ACME Export SARL
Rue des Docks, Douala
Destinataire
Cameroun Import SA
Avenue Kennedy, Yaounde
Declarant
Transit Express
Montant total 1500,50 XAF
Points et elements de machines 84713000 quantite 12.50
Pieces detachees pour vehicules 87089900 poids 300,25
DDI 1000 20.00 200.00
TVA 1200 19,25 231,00
DDI 500 10.00 50.00
"""


class TestParser:
    def test_parse_declaration_full(self, capsys):
        res = parser.parse_declaration(DECLARATION_TEXT)
        assert res["declaration_number"] == "OW110"
        assert res["bureau"].startswith("DOUALA PORT")
        assert res["currency"] == "XAF"
        assert res["expediteur"]["name"] == "ACME Export SARL"
        assert res["expediteur"]["address"]
        assert res["destinataire"]["name"] == "Cameroun Import SA"
        assert res["declarant"]["name"] == "Transit Express"
        assert res["declarant"]["identifier"] is None
        assert [i["hs_code"] for i in res["items"]] == ["84713000", "87089900"]
        assert res["items"][0]["description"] == "Points et elements de machines"
        assert res["items"][0]["price"] == 1500.5
        assert res["items"][1]["price"] == 12.5
        taxes = {(t["type"], t["rate"], t["amount"]) for t in res["taxes"]}
        assert taxes == {("DDI", 20.0, 200.0), ("DDI", 10.0, 50.0), ("TVA", 19.25, 231.0)}
        assert res["raw_text_preview"] == DECLARATION_TEXT
        out = capsys.readouterr().out
        assert "OW110" in out and "Items found: 2" in out and "Taxes found: 3" in out

    def test_parse_declaration_empty_and_preview_truncation(self):
        empty = parser.parse_declaration("")
        assert empty["declaration_number"] is None
        assert empty["bureau"] is None
        assert empty["currency"] is None
        assert empty["items"] == [] and empty["taxes"] == []
        assert empty["expediteur"] == {"name": None, "address": None, "identifier": None}

        long_text = "x" * 800
        assert len(parser.parse_declaration(long_text)["raw_text_preview"]) == 500

    def test_extract_declaration_number_fallback_pattern(self):
        assert parser.extract_declaration_number("ref ab12345 ici") == "AB12345"
        assert parser.extract_declaration_number("rien du tout") is None

    def test_extract_bureau_variants(self):
        assert parser.extract_bureau("Bureau: KRIBI SUD\n") == "KRIBI SUD"
        assert parser.extract_bureau("nothing") is None

    def test_extract_party_info_single_line(self):
        party = parser.extract_party_info("Box 8", ["Destinataire", "Box 8"])
        assert party.name is None
        assert party.address == "Box"
        assert parser.extract_party_info("abc", ["Box 2"]) == parser.Party()

    def test_extract_hs_codes_unique(self):
        assert parser.extract_hs_codes("123456 12345 123456 1234567890 12345678901") == [
            "123456",
            "1234567890",
        ]

    def test_extract_items_limit_and_missing_fields(self):
        text = " ".join(str(100000 + i) for i in range(7))
        items = parser.extract_items(text)
        assert len(items) == 5
        assert all(i.description is None and i.price is None for i in items)

    def test_extract_taxes_unparseable_rate(self):
        taxes = parser.extract_taxes("TCI 100 1.2.3 4,5")
        assert len(taxes) == 1
        assert taxes[0].type == "TCI"
        assert taxes[0].rate is None and taxes[0].amount is None

    def test_extract_currency(self):
        assert parser.extract_currency("paid in eur") == "EUR"
        assert parser.extract_currency("no money") is None


# ---------------------------------------------------------------------------
# preprocessing / table_extraction / types (pure OpenCV, no binaries)
# ---------------------------------------------------------------------------


def _text_like_image(h=60, w=90):
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    img[25:35, 10:80] = 0  # a dark horizontal band, like a line of text
    return img


class TestPreprocessing:
    def test_require_cv2_missing(self, monkeypatch):
        monkeypatch.setattr(preprocessing, "cv2", None)
        for fn in (
            preprocessing.to_gray,
            preprocessing.binarize,
            preprocessing.denoise,
            preprocessing.deskew,
            preprocessing.enhance_contrast,
            preprocessing.preprocess_for_ocr,
        ):
            with pytest.raises(RuntimeError, match="OpenCV"):
                fn(np.zeros((4, 4), dtype=np.uint8))

    def test_to_gray(self):
        gray = np.zeros((4, 5), dtype=np.uint8)
        assert preprocessing.to_gray(gray) is gray
        assert preprocessing.to_gray(np.zeros((4, 5, 3), dtype=np.uint8)).shape == (4, 5)

    def test_binarize_denoise_contrast_shapes(self):
        img = _text_like_image()
        for fn in (preprocessing.binarize, preprocessing.denoise, preprocessing.enhance_contrast):
            out = fn(img)
            assert out.shape == (60, 90)
            assert out.dtype == np.uint8
        assert set(np.unique(preprocessing.binarize(img))) <= {0, 255}

    def test_deskew_blank_image_returned_as_is(self):
        blank = np.full((20, 20), 255, dtype=np.uint8)
        assert preprocessing.deskew(blank) is blank

    @pytest.mark.parametrize("angle", [-60.0, 5.0])
    def test_deskew_angle_branches(self, monkeypatch, angle):
        real = preprocessing.cv2.minAreaRect
        seen = {}

        def fake_min_area_rect(coords):
            center, size, _ = real(coords)
            return center, size, angle

        real_rot = preprocessing.cv2.getRotationMatrix2D

        def spy_rot(center, a, scale):
            seen["angle"] = a
            return real_rot(center, a, scale)

        monkeypatch.setattr(preprocessing.cv2, "minAreaRect", fake_min_area_rect)
        monkeypatch.setattr(preprocessing.cv2, "getRotationMatrix2D", spy_rot)
        img = _text_like_image()[..., 0].copy()
        out = preprocessing.deskew(img)
        assert out.shape == img.shape
        assert seen["angle"] == (-(90 + angle) if angle < -45 else -angle)

    def test_preprocess_for_ocr_upscales_small_images(self):
        out = preprocessing.preprocess_for_ocr(_text_like_image(60, 90))
        assert out.shape == (1200, 1800)
        assert set(np.unique(out)) <= {0, 255}


class TestTableExtraction:
    def test_require_cv2_missing(self, monkeypatch):
        monkeypatch.setattr(table_extraction, "cv2", None)
        with pytest.raises(RuntimeError, match="OpenCV"):
            table_extraction.detect_tables_by_lines(np.zeros((4, 4), dtype=np.uint8))

    def test_detects_wide_rectangle_in_colour_image(self):
        img = np.full((300, 600, 3), 255, dtype=np.uint8)
        img[50:53, 20:560] = 0
        img[147:150, 20:560] = 0
        img[50:150, 20:23] = 0
        img[50:150, 557:560] = 0
        tables = table_extraction.detect_tables_by_lines(img)
        assert len(tables) == 1
        x, y, w, h = tables[0]["bbox"]
        assert w > 500 and 90 < h < 120
        assert tables[0]["rows"] == []

    def test_ignores_small_and_tall_shapes(self):
        img = np.full((400, 400), 255, dtype=np.uint8)
        img[10:20, 10:30] = 0  # too small
        img[50:350, 300:305] = 0  # large area but tall, not wide
        img[50:350, 340:345] = 0
        img[50:53, 300:345] = 0
        img[347:350, 300:345] = 0
        assert table_extraction.detect_tables_by_lines(img) == []


def test_types_to_dict_roundtrip():
    page = PageResult(
        page_index=0,
        width=10,
        height=20,
        text="t",
        words=[Word("a", BBox(1, 2, 3, 4), 90.0), Word("b")],
    )
    doc = DocumentResult(
        source="s", num_pages=1, pages=[page], normalized=NormalizedFields(dates=["2024-01-01"])
    )
    d = doc.to_dict()
    assert d["pages"][0]["words"] == [
        {"text": "a", "bbox": [1, 2, 3, 4], "conf": 90.0},
        {"text": "b", "bbox": None, "conf": None},
    ]
    assert d["normalized"] == {
        "dates": ["2024-01-01"],
        "amounts": [],
        "currencies": [],
        "vendor": None,
    }
    assert d["cer"] is None and d["warnings"] == []
