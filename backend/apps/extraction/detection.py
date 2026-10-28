"""Détection du type d'une pièce déposée d'après le titre de sa première page (LEC-07).

Lecture rapide de la seule première page d'un PDF texte, après le contrôle antivirus. Une image,
un classeur ou un PDF sans texte ne donnent rien : le nom du fichier sert alors d'indice faible.
Une erreur de lecture n'empêche jamais le dépôt.
"""

import logging

from apps.documents.sniff import PDF
from apps.documents.storage import get_storage
from apps.regulations.classification import suggest_document_type

from .readers import detect_type

logger = logging.getLogger(__name__)


def detect_document_type(document) -> dict | None:
    if document.mime == PDF:
        try:
            import pdfplumber

            from .adapters.pdf_words import page_words
            from .adapters.words import rows_from_words

            with pdfplumber.open(get_storage().path_for_reading(document.object_key)) as pdf:
                if pdf.pages:
                    page = pdf.pages[0]
                    words = page_words(page)
                    if words:
                        rows = rows_from_words(
                            words, page_number=1, width=float(page.width), height=float(page.height),
                            rotation=int(page.rotation or 0),
                        )  # fmt: skip
                        if found := detect_type([rows]):
                            return found
        except Exception:
            logger.info("Type detection skipped for document %s", document.id, exc_info=True)
    hint = suggest_document_type(document.original_name)
    if hint["suggested_type"]:
        return {"code": hint["suggested_type"], "method": "filename", "excerpt": document.original_name[:80]}
    return None
