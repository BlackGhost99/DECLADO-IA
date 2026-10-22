"""Adaptateurs d'extraction : chacun lit un format et rend le schéma commun (schema.py)."""

from collections.abc import Callable
from pathlib import Path

from apps.documents.sniff import JPEG, PDF, PNG, XLSX

from ..schema import ParsedDocument

PARSER_VERSION = "1.0"
SCHEMA_VERSION = "1"

Progress = Callable[[str, int, int], None]


class ExtractionFailure(Exception):
    """Échec récupérable, expliqué à l'utilisateur ; la saisie manuelle reste possible."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


def parser_for(mime: str, *, ocr: bool) -> str:
    if mime == XLSX:
        return "xlsx"
    if mime in (PNG, JPEG):
        return "ocr"
    if mime == PDF:
        return "pdf_text+ocr" if ocr else "pdf_text"
    raise ExtractionFailure("UNSUPPORTED_TYPE", "Ce type de pièce n'est pas extractible.")


def run(mime: str, path: Path, *, ocr: bool, progress: Progress) -> ParsedDocument:
    from . import ocr as ocr_adapter
    from . import pdf_text, xlsx

    if mime == XLSX:
        return xlsx.extract(path, progress=progress)
    if mime in (PNG, JPEG):
        if not ocr:
            raise ExtractionFailure(
                "OCR_REQUIRED", "Image : la lecture demande l'OCR. Relancer avec l'OCR ou saisir les lignes."
            )
        return ocr_adapter.extract_image(path, progress=progress)
    if mime == PDF:
        return pdf_text.extract(path, ocr=ocr, progress=progress)
    raise ExtractionFailure("UNSUPPORTED_TYPE", "Ce type de pièce n'est pas extractible.")
