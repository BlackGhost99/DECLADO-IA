from __future__ import annotations

import logging
import os
from typing import Iterator, Optional

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency for OCR
    pdfplumber = None

try:
    from pdf2image import convert_from_path  # type: ignore
except ImportError:  # pragma: no cover
    convert_from_path = None

logger = logging.getLogger(__name__)


def _find_poppler_bin() -> Optional[str]:
    """Try to locate Poppler's bin directory on Windows.

    Returns the path to the bin directory if found (containing pdfinfo.exe), else None.
    """
    # 1) Respect an environment variable if provided
    env_path = os.environ.get("POPPLER_PATH") or os.environ.get("POPPLER_BIN")
    if env_path and os.path.exists(os.path.join(env_path, "pdfinfo.exe")):
        return env_path

    # 2) Check PATH entries explicitly (user may have added Poppler to PATH)
    path_env = os.environ.get("PATH", "")
    for entry in path_env.split(os.pathsep):
        if not entry:
            continue
        try:
            if os.path.exists(os.path.join(entry, "pdfinfo.exe")):
                return entry
        except Exception:
            pass

    # 3) Common installation locations
    candidates = [
        r"C:\\Release-25.11.0-0\\poppler-25.11.0\\Library\\bin",  # User's custom installation
        r"C:\\Program Files\\poppler\\Library\\bin",
        r"C:\\Program Files\\poppler\\bin",
        r"C:\\Program Files (x86)\\poppler\\Library\\bin",
        r"C:\\ProgramData\\chocolatey\\lib\\poppler\\tools",
    ]

    for c in candidates:
        if os.path.exists(os.path.join(c, "pdfinfo.exe")):
            return c

    # 4) Try to scan Program Files for folders starting with "poppler"
    try:
        for root in [r"C:\\Program Files", r"C:\\Program Files (x86)"]:
            if not os.path.exists(root):
                continue
            for name in os.listdir(root):
                if name.lower().startswith("poppler"):
                    # check both bin and Library/bin layouts
                    bins = [
                        os.path.join(root, name, "Library", "bin"),
                        os.path.join(root, name, "bin"),
                    ]
                    for b in bins:
                        if os.path.exists(os.path.join(b, "pdfinfo.exe")):
                            return b
    except Exception:
        # best-effort discovery only
        pass

    return None


def _require_pdfplumber() -> None:
    if pdfplumber is None:
        raise RuntimeError(
            "pdfplumber n'est pas installé. Installez pdfplumber pour traiter les PDF digitaux."
        )


def _require_pdf2image() -> None:
    if convert_from_path is None:
        raise RuntimeError(
            "pdf2image n'est pas installé. Installez pdf2image + poppler pour rasteriser les PDF."
        )


def iter_pdf_pages_as_images(
    pdf_path: str, dpi: int = 300
) -> Iterator[tuple[int, "PIL.Image.Image"]]:
    """Yield (page_index, PIL Image) for each page in the PDF.

    Uses pdf2image to rasterize pages when OCR is required (scanned PDFs).
    """
    _require_pdf2image()
    poppler_bin = _find_poppler_bin()
    if poppler_bin:
        logger.info(f"Poppler detected at: {poppler_bin}")
        images = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_bin)
    else:
        logger.warning(
            "Poppler not found in POPPLER_PATH or PATH; calling convert_from_path without poppler_path"
        )
        # Let pdf2image raise a clear error; caller may catch and surface a helpful message
        images = convert_from_path(pdf_path, dpi=dpi)
    for idx, img in enumerate(images):
        yield idx, img


def extract_pdf_text_and_tables(pdf_path: str):
    """Extract text and tables using pdfplumber for digital PDFs."""
    _require_pdfplumber()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            yield i, text, tables
