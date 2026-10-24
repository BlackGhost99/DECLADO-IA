"""OCR à la demande (Tesseract) : pages scannées et images (DEV-015).

Chaque mot garde sa confiance ; un nombre lu avec peu de confiance reste inconnu. Les échecs
(OCR absent, délai dépassé, image démesurée) sont récupérables et laissent la saisie manuelle.
"""

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps

from ..language import annotate_parsed
from ..layout import Page, structure
from ..schema import Origin, ParsedDocument, warning
from . import ExtractionFailure, Progress
from .words import rows_from_words

# Plafond de pixels : une image piégée ne doit pas épuiser la mémoire du worker.
Image.MAX_IMAGE_PIXELS = 60_000_000
RENDER_DPI = 300


@dataclass
class OcrResult:
    page: Page | None
    warnings: list[dict] = field(default_factory=list)


def _languages(locale_hint: str = "") -> str:
    import pytesseract

    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception as exc:  # binaire absent ou inutilisable
        raise ExtractionFailure(
            "OCR_UNAVAILABLE", "L'OCR n'est pas installé sur le serveur : saisir les lignes manuellement."
        ) from exc
    wanted = [lang for lang in settings.OCR_LANGUAGES.split("+") if lang in installed]
    if not wanted:
        raise ExtractionFailure(
            "OCR_UNAVAILABLE",
            f"Langues OCR {settings.OCR_LANGUAGES} absentes du serveur : saisir les lignes manuellement.",
        )
    # A trusted hint only prioritizes a corresponding installed language; it never disables fallback packs.
    hints = {"fr": "fra", "en": "eng", "es": "spa", "ar": "ara"}
    preferred = hints.get(locale_hint)
    if preferred in wanted:
        wanted = [preferred] + [item for item in wanted if item != preferred]
    return "+".join(wanted)


def _script_hint(osd: str) -> str:
    """Tesseract OSD is a script hint only, not a guarantee of text language."""
    import re

    match = re.search(r"^Script:\\s*(\\w+)", osd, flags=re.MULTILINE)
    if not match:
        return ""
    if match.group(1).lower() == "arabic":
        return "ar"
    return ""


def _detect_script(image: Image.Image) -> str:
    """Best-effort prior to OCR; failures never prevent regular recognition."""
    import pytesseract

    try:
        return _script_hint(pytesseract.image_to_osd(image, timeout=min(settings.OCR_PAGE_TIMEOUT_SECONDS, 10)))
    except (RuntimeError, ValueError, pytesseract.TesseractError):
        return ""


def ocr_image(image: Image.Image, *, page_number: int, locale_hint: str = "") -> OcrResult:
    import pytesseract

    image = ImageOps.exif_transpose(image).convert("L")
    if not locale_hint:
        locale_hint = _detect_script(image)
    lang = _languages(locale_hint=locale_hint)
    try:
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=settings.OCR_PAGE_TIMEOUT_SECONDS,
        )
    except RuntimeError:  # délai dépassé
        return OcrResult(
            None,
            [
                warning(
                    "OCR_TIMEOUT", f"Page {page_number} : OCR interrompu (délai dépassé). Relancer.", page=page_number
                )
            ],
        )
    words = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        left, top, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"text": text, "x0": left, "x1": left + w, "top": top, "bottom": top + h, "confidence": conf})
    warnings = []
    if not words:
        warnings.append(warning("OCR_NO_TEXT", f"Page {page_number} : aucun texte reconnu.", page=page_number))
        return OcrResult(None, warnings)
    page = rows_from_words(words, page_number=page_number, width=image.width, height=image.height)
    page.origin = Origin.OCR
    low = [w for w in words if w["confidence"] < 60]
    if len(low) > len(words) / 3:
        warnings.append(
            warning(
                "OCR_LOW_QUALITY",
                f"Page {page_number} : lecture peu sûre sur {len(low)} mots sur {len(words)}. Vérifier chaque valeur.",
                page=page_number,
            )
        )
    return OcrResult(page, warnings)


def ocr_pdf_page(path: Path, number: int) -> OcrResult:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        bitmap = pdf[number - 1].render(scale=RENDER_DPI / 72)
        image = bitmap.to_pil()
    finally:
        pdf.close()
    return ocr_image(image, page_number=number)


def extract_image(path: Path, *, progress: Progress) -> ParsedDocument:
    progress("OCR", 0, 1)
    try:
        with Image.open(path) as image:
            image.load()
            result = ocr_image(image, page_number=1)
    except Image.DecompressionBombError as exc:
        raise ExtractionFailure("IMAGE_TOO_LARGE", "Image trop grande pour être lue sans risque.") from exc
    except (OSError, SyntaxError) as exc:
        raise ExtractionFailure("DOCUMENT_UNREADABLE", "Image illisible : déposer une version lisible.") from exc
    progress("structuration", 1, 1)
    pages = [result.page] if result.page else []
    doc = structure(pages, origin=Origin.OCR)
    annotate_parsed(doc, pages)
    doc.warnings.extend(result.warnings)
    doc.stats.update({"pages": 1, "text_pages": 0, "ocr_pages": [1] if result.page else [], "pages_without_text": []})
    return doc
