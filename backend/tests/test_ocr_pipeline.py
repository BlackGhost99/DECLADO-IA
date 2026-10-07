import os
import shutil
import tempfile

import pytest

from app.ocr_pipeline.normalize import normalize_amounts, normalize_currencies, normalize_date
from app.ocr_pipeline.pipeline import run_document


def test_normalize_amounts_and_currency_and_dates():
    text = "Facture du 12/01/2024 montant 1 500,50 EUR (ou 1500.50 $)"
    amts = normalize_amounts(text)
    curr = normalize_currencies(text)
    dates = normalize_date(text)
    assert any(abs(a - 1500.50) < 0.01 for a in amts)
    assert "EUR" in curr and "USD" in curr
    assert "2024-01-12" in dates


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_run_document_on_small_image(tmp_path):
    # Create a simple synthetic image with text using PIL
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        pytest.skip("Pillow not available")

    # Police de 40 px : la police bitmap par défaut (11 px) est illisible pour Tesseract.
    img = Image.new("RGB", (1000, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 70), "Invoice 123 total 45.67 USD", fill=(0, 0, 0), font=ImageFont.load_default(size=40))
    fp = tmp_path / "sample.png"
    img.save(fp)

    res = run_document(str(fp), lang="eng")
    assert res["num_pages"] == 1
    assert isinstance(res["normalized"], dict)
    # Heuristic checks
    assert any(abs(a - 45.67) < 0.01 for a in res["normalized"].get("amounts", []))
    assert "USD" in res["normalized"].get("currencies", [])
