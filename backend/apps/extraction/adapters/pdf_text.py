"""PDF avec couche texte (pdfplumber) ; pages sans texte lues par OCR seulement sur demande."""

from pathlib import Path

from django.conf import settings

from ..layout import structure
from ..schema import ParsedDocument, warning
from . import ExtractionFailure, Progress
from .words import rows_from_words

MIN_TEXT_CHARS = 20


def _open(path: Path):
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        return pdfplumber.open(path)
    except (PDFPasswordIncorrect, PdfminerException) as exc:
        if "password" in repr(exc).lower() or isinstance(exc, PDFPasswordIncorrect):
            raise ExtractionFailure(
                "DOCUMENT_PROTECTED", "PDF protégé par mot de passe : déposer une version lisible."
            ) from exc
        raise ExtractionFailure("DOCUMENT_UNREADABLE", "PDF illisible : déposer une version lisible.") from exc
    except Exception as exc:  # structure PDF cassée
        raise ExtractionFailure("DOCUMENT_UNREADABLE", "PDF illisible : déposer une version lisible.") from exc


def extract(path: Path, *, ocr: bool, progress: Progress) -> ParsedDocument:
    from . import ocr as ocr_adapter

    pdf = _open(path)
    with pdf:
        try:
            count = len(pdf.pages)
        except Exception as exc:
            raise ExtractionFailure("DOCUMENT_UNREADABLE", "PDF illisible : déposer une version lisible.") from exc
        limit = settings.EXTRACTION_MAX_PAGES
        if count > limit:
            raise ExtractionFailure(
                "PAGE_LIMIT", f"{count} pages : la limite est de {limit} pages par facture.", pages=count, limit=limit
            )
        pages, without_text, ocr_pages, warnings = [], [], [], []
        for number, page in enumerate(pdf.pages, start=1):
            progress("lecture du texte", number - 1, count)
            try:
                words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=2)
            except Exception as exc:
                raise ExtractionFailure(
                    "DOCUMENT_UNREADABLE", f"Page {number} illisible : déposer une version lisible.", page=number
                ) from exc
            if sum(len(w["text"]) for w in words) >= MIN_TEXT_CHARS:
                pages.append(
                    rows_from_words(
                        words, page_number=number, width=float(page.width), height=float(page.height),
                        rotation=int(page.rotation or 0),
                    )
                )  # fmt: skip
                continue
            without_text.append(number)
            if ocr:
                progress("OCR", number - 1, count)
                result = ocr_adapter.ocr_pdf_page(path, number)
                if result.page is not None:
                    pages.append(result.page)
                    ocr_pages.append(number)
                warnings.extend(result.warnings)
        progress("structuration", count, count)
    doc = structure(pages)
    doc.warnings.extend(warnings)
    if without_text and not ocr:
        doc.warnings.append(
            warning(
                "OCR_REQUIRED",
                "Pages sans texte lisible : relancer avec l'OCR pour les lire, ou saisir les lignes.",
                pages=without_text,
            )
        )
    doc.stats.update({"pages": count, "text_pages": count - len(without_text), "ocr_pages": ocr_pages,
                      "pages_without_text": without_text})  # fmt: skip
    return doc
