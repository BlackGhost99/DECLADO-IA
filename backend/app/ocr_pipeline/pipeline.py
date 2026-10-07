from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency on workstation
    cv2 = None  # lazy guard so the backend can start without OpenCV

import numpy as np
from PIL import Image

from .normalize import normalize_amounts, normalize_currencies, normalize_date
from .ocr_engine import ocr_image
from .pdf_utils import extract_pdf_text_and_tables, iter_pdf_pages_as_images
from .preprocessing import preprocess_for_ocr
from .table_extraction import detect_tables_by_lines
from .types import DocumentResult, NormalizedFields, PageResult

logger = logging.getLogger(__name__)


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV (cv2) n'est pas installé. Installez opencv-python pour activer l'OCR."
        )


def _pil_to_cv(img: Image.Image) -> np.ndarray:
    _require_cv2()
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _compute_cer(hyp: str, ref: str) -> float:
    # simple Levenshtein distance
    if not ref:
        return 0.0
    m = len(ref)
    n = len(hyp)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    dist = dp[n]
    return dist / m


def _ocr_page(img: np.ndarray, page_index: int, lang: str) -> PageResult:
    """Prétraite et lit une page ; journalise la durée de chaque étape."""
    t0 = time.perf_counter()
    proc = preprocess_for_ocr(img)
    t1 = time.perf_counter()
    txt, words = ocr_image(proc, lang=lang)
    t2 = time.perf_counter()
    h, w = proc.shape[:2]
    tables = detect_tables_by_lines(proc)
    logger.info(
        "OCR page %d (%dx%d) : prétraitement %.2f s, tesseract %.2f s, tableaux %.2f s",
        page_index,
        w,
        h,
        t1 - t0,
        t2 - t1,
        time.perf_counter() - t2,
    )
    return PageResult(
        page_index=page_index, width=w, height=h, text=txt, words=words, tables=tables
    )


def run_document(path: str, lang: str = "eng+fra") -> dict:
    """Run OCR pipeline on a document (image or PDF). Return normalized JSON dict."""
    p = Path(path)
    pages: list[PageResult] = []
    warnings: list[str] = []

    if p.suffix.lower() in {".pdf"}:
        # Try digital PDF extraction first
        for idx, text, tables in extract_pdf_text_and_tables(str(p)):
            # If no text (likely scanned), fallback to OCR via rasterization
            if not text.strip():
                try:
                    for idx2, pil_img in iter_pdf_pages_as_images(str(p)):
                        pages.append(_ocr_page(_pil_to_cv(pil_img), idx2, lang))
                except Exception as e:
                    # Poppler not installed - can't convert PDF to images
                    warnings.append(f"Erreur conversion PDF en images: {str(e)}")
                    warnings.append(
                        "Installez Poppler: https://github.com/oschwartz10612/poppler-windows/releases/"
                    )
                    # Use the digital text we already have
                    pages.append(
                        PageResult(
                            page_index=idx,
                            width=0,
                            height=0,
                            text=text,
                            words=[],
                            tables=[{"rows": t} for t in tables],
                        )
                    )
            else:
                # Digital text: build page result with tables
                # Use page size approximation (unknown from pdfplumber here)
                pages.append(
                    PageResult(
                        page_index=idx,
                        width=0,
                        height=0,
                        text=text,
                        words=[],
                        tables=[{"rows": t} for t in tables],
                    )
                )
    else:
        # Image file
        pil_img = Image.open(str(p))
        pages.append(_ocr_page(_pil_to_cv(pil_img), 0, lang))

    # Normalization from concatenated text
    full_text = "\n".join(pg.text for pg in pages)
    normalized = NormalizedFields(
        dates=normalize_date(full_text),
        amounts=normalize_amounts(full_text),
        currencies=normalize_currencies(full_text),
        vendor=None,
    )

    # CER baseline if ground-truth exists (same basename + .gt.txt)
    cer = None
    gt_file = p.with_suffix("").as_posix() + ".gt.txt"
    if os.path.exists(gt_file):
        with open(gt_file, encoding="utf-8", errors="ignore") as f:
            ref = f.read().strip()
        cer = _compute_cer(full_text, ref)

    result = DocumentResult(
        source=str(p),
        num_pages=len(pages),
        pages=pages,
        normalized=normalized,
        cer=cer,
        warnings=warnings,
    )
    return result.to_dict()


def run_batch(input_dir: str, output_dir: str, lang: str = "eng+fra") -> list[str]:
    """Process all PDFs/images in input_dir and write JSON outputs to output_dir.
    Returns list of output file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    outs: list[str] = []
    exts = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    for root, _, files in os.walk(input_dir):
        for fn in files:
            if Path(fn).suffix.lower() in exts:
                src = os.path.join(root, fn)
                res = run_document(src, lang=lang)
                out = os.path.join(output_dir, Path(fn).with_suffix(".json").name)
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False, indent=2)
                outs.append(out)
    return outs
