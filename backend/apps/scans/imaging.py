"""Images des pages numérisées : découpage des fichiers, recadrage, page blanche, lecture du texte.

Aucune valeur n'est inventée : une page dont le texte n'a pas pu être lu est signalée « peu
lisible » et reste disponible pour une reprise ou une saisie manuelle.
"""

import io
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageFilter, ImageOps, ImageSequence

from apps.documents.sniff import JPEG, PDF, PNG, TIFF
from apps.extraction.adapters import ExtractionFailure
from apps.extraction.adapters.ocr import _languages
from apps.extraction.adapters.pdf_words import page_words

from .titles import Word

Image.MAX_IMAGE_PIXELS = 60_000_000
RENDER_DPI = 200  # image conservée pour l'aperçu et l'assemblage de la pièce
OCR_DPI = 300
MAX_SIDE = 2400  # plus grand côté conservé, en pixels
THUMB_SIDE = 260


class PageError(Exception):
    """Page impossible à ouvrir : signalée, sans bloquer les autres pages du lot."""


@dataclass
class LoadedPage:
    image: Image.Image
    words: list[Word] | None = None  # texte natif du PDF, s'il existe
    notes: list[str] = field(default_factory=list)


def page_count(path: Path, mime: str) -> int:
    if mime == PDF:
        import pypdfium2 as pdfium

        try:
            pdf = pdfium.PdfDocument(str(path))
        except pdfium.PdfiumError as exc:
            raise PageError("PDF illisible ou protégé.") from exc
        try:
            return len(pdf)
        finally:
            pdf.close()
    if mime == TIFF:
        with Image.open(path) as image:
            return getattr(image, "n_frames", 1)
    return 1


def _fit(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


def _pdf_words(path: Path, number: int) -> list[Word]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        page = pdf.pages[number - 1]
        height, width = float(page.height) or 1.0, float(page.width) or 1.0
        return [Word(w["text"], float(w["top"]) / height, float(w["x0"]) / width) for w in page_words(page)]


def load_page(path: Path, mime: str, number: int) -> LoadedPage:
    try:
        if mime == PDF:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(path))
            try:
                image = pdf[number - 1].render(scale=RENDER_DPI / 72).to_pil()
            finally:
                pdf.close()
            words = _pdf_words(path, number)
            return LoadedPage(_fit(image), words or None)
        with Image.open(path) as source:
            if mime == TIFF:
                frame = next(f for i, f in enumerate(ImageSequence.Iterator(source), start=1) if i == number)
                image = frame.copy()
            else:
                source.load()
                image = ImageOps.exif_transpose(source)
            return LoadedPage(_fit(image))
    except Image.DecompressionBombError as exc:
        raise PageError("Image trop grande pour être lue sans risque.") from exc
    except (OSError, SyntaxError, StopIteration, IndexError) as exc:
        raise PageError("Page illisible.") from exc


def crop_document(image: Image.Image) -> tuple[Image.Image, bool]:
    """Photo : garde la feuille (zone claire) et retire le fond plus sombre autour, si elle se détache nettement."""
    gray = ImageOps.autocontrast(image.convert("L"))
    small = gray.copy()
    small.thumbnail((400, 400))
    small = small.filter(ImageFilter.MedianFilter(5))
    mask = small.point(lambda v: 255 if v > 150 else 0)
    box = mask.getbbox()
    if box is None:
        return image, False
    area = (box[2] - box[0]) * (box[3] - box[1]) / (small.width * small.height)
    if not 0.25 <= area <= 0.95:
        return image, False
    sx, sy = image.width / small.width, image.height / small.height
    margin = 4
    crop = (
        max(0, int(box[0] * sx) - margin),
        max(0, int(box[1] * sy) - margin),
        min(image.width, int(box[2] * sx) + margin),
        min(image.height, int(box[3] * sy) + margin),
    )
    return image.crop(crop), True


def is_blank(image: Image.Image) -> bool:
    """Page sans encre : après suppression des poussières isolées, presque aucun pixel sombre.

    Seuil bas exprès : une seule ligne de texte suffit à garder la page (dans le doute, on garde).
    """
    gray = image.convert("L")
    gray.thumbnail((1000, 1000))
    gray = gray.filter(ImageFilter.MedianFilter(3))
    dark = sum(gray.histogram()[:200])
    total = gray.width * gray.height or 1
    return dark / total < 0.0001


@dataclass
class OcrText:
    words: list[Word]
    confidence: float | None  # moyenne des confiances Tesseract, pour signaler une lecture douteuse
    rotation: int = 0


def _orientation(image: Image.Image) -> tuple[int, bool]:
    """Rotation (sens horaire) qui remet le texte droit selon Tesseract, et si l'avis est net."""
    import pytesseract

    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT, timeout=30)
    except Exception:  # page trop pauvre en texte, ou OSD absent : pas d'avis
        return 0, False
    return int(osd.get("rotate", 0)) % 360, float(osd.get("orientation_conf", 0)) >= 2


def _read(gray: Image.Image, lang: str, rotation: int) -> OcrText:
    import pytesseract

    if rotation:
        gray = gray.rotate(-rotation, expand=True)
    scale = OCR_DPI / RENDER_DPI
    if scale > 1 and max(gray.size) * scale <= 4000:
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)))
    try:
        data = pytesseract.image_to_data(
            gray, lang=lang, output_type=pytesseract.Output.DICT, timeout=settings.OCR_PAGE_TIMEOUT_SECONDS
        )
    except RuntimeError as exc:
        raise ExtractionFailure("OCR_TIMEOUT", "Lecture interrompue (délai dépassé).") from exc
    words, confidences = [], []
    height, width = gray.height or 1, gray.width or 1
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append(Word(text, data["top"][i] / height, data["left"][i] / width))
        confidences.append(conf)
    mean = sum(confidences) / len(confidences) if confidences else None
    return OcrText(words, mean, rotation)


DOUBTFUL_CONFIDENCE = 60  # en dessous, on essaie aussi l'autre sens de la page


def ocr_words(image: Image.Image, *, detect_orientation: bool = True) -> OcrText:
    """Lit la page avec Tesseract. Lève ExtractionFailure si l'OCR n'est pas installé.

    Sens de lecture : celui de Tesseract quand son avis est net ; sinon la page est lue telle
    quelle et, si la lecture est douteuse, aussi dans le sens suggéré ou retournée, et la
    lecture la plus sûre est gardée.
    """
    lang = _languages()
    gray = image.convert("L")
    suggested, sure = _orientation(gray) if detect_orientation else (0, True)
    best = _read(gray, lang, suggested if sure else 0)
    if sure or (best.confidence or 0) >= DOUBTFUL_CONFIDENCE:
        return best
    for rotation in dict.fromkeys(r for r in (suggested, 180) if r):
        other = _read(gray, lang, rotation)
        if (other.confidence or 0) > (best.confidence or 0):
            best = other
    return best


def jpeg_bytes(image: Image.Image, *, rotation: int = 0, side: int | None = None) -> bytes:
    if rotation:
        image = image.rotate(-rotation, expand=True)
    if side:
        image = image.copy()
        image.thumbnail((side, side))
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


def pdf_bytes(images: list[Image.Image]) -> bytes:
    """Assemble les pages d'une pièce en un PDF (images seules ; la lecture se fait ensuite par OCR)."""
    pages = [im.convert("RGB") for im in images]
    out = io.BytesIO()
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=RENDER_DPI)
    return out.getvalue()


ACCEPTED_SOURCES = (PDF, PNG, JPEG, TIFF)
