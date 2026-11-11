"""Lecture bornée des pièces pour le dépôt groupé, après contrôle du fichier."""

import logging

from django.conf import settings

from apps.documents.models import Document
from apps.documents.sniff import JPEG, PDF, PNG, Readability
from apps.documents.storage import get_storage
from apps.extraction import adapters, readers
from apps.extraction.adapters import ocr, pdf_text
from apps.extraction.adapters.pdf_words import page_words
from apps.extraction.adapters.words import rows_from_words
from apps.extraction.schema import Status
from apps.regulations.classification import suggest_document_type

logger = logging.getLogger(__name__)
PREVIEW_PAGES = 6
OCR_TIMEOUT = 15

REFERENCES = {
    readers.INVOICE: (("invoice_number", "invoice", "own"), ("related_bl", "bl", "cited")),
    readers.TRANSPORT: (("transport_number", "bl", "own"), ("related_invoice", "invoice", "cited")),
}
CITED = (("related_invoice", "invoice", "cited"), ("related_bl", "bl", "cited"))
PARTY = {readers.INVOICE: "buyer_name", readers.INSURANCE: "insured"}
SHIPMENT_FIELDS = ("shipper", "vessel", "voyage", "packages", "gross_weight")


def _pdf_pages(path, *, allow_ocr):
    with pdf_text._open(path) as pdf:
        if len(pdf.pages) > settings.EXTRACTION_MAX_PAGES:
            raise adapters.ExtractionFailure("PAGE_LIMIT", "PDF trop long pour la lecture automatique.")
        pages = []
        for page in pdf.pages[:PREVIEW_PAGES]:
            words = page_words(page)
            if sum(len(word["text"]) for word in words) >= pdf_text.MIN_TEXT_CHARS:
                pages.append(
                    rows_from_words(
                        words,
                        page_number=page.page_number,
                        width=float(page.width),
                        height=float(page.height),
                        rotation=int(page.rotation or 0),
                    )
                )
    if pages or not allow_ocr:
        return pages, "native" if pages else "ocr_required"
    result = ocr.ocr_pdf_page(path, 1, timeout=OCR_TIMEOUT)
    if result.page:
        return [result.page], "ocr"
    return [], _empty_ocr_status(result.warnings)


def _empty_ocr_status(warnings):
    return "ocr_failed" if any(w["code"] == "OCR_TIMEOUT" for w in warnings) else "no_text"


def _preview(document, *, allow_ocr):
    code = suggest_document_type(document.original_name)["suggested_type"]
    hint = {"code": code, "method": "filename", "excerpt": document.original_name[:80]} if code else {}
    result = {"detection": hint, "party": "", "references": [], "shipment": {}, "reading_status": "no_text"}
    if document.readability != Readability.OK:
        result["reading_status"] = "protected" if document.readability == Readability.PROTECTED else "failed"
        return result

    try:
        path = get_storage().path_for_reading(document.object_key)
        pages = []
        if document.mime == PDF:
            pages, status = _pdf_pages(path, allow_ocr=allow_ocr)
        elif document.mime in (PNG, JPEG):
            # Le parcours groupé laisse la lecture OCR des images à l'action dédiée du dossier.
            status = "ocr_required"
        else:
            reader = readers.READER_FOR_TYPE.get(code, readers.INVOICE)
            parsed = adapters.run(document.mime, path, ocr=False, progress=lambda *_: None, reader=reader)
            status = "native" if any(not line.startswith("[") for line in parsed.text.splitlines()) else "no_text"
            result["reading_status"] = status
            if code and status == "native":
                _collect(result, parsed.header, reader)
            return result

        result["reading_status"] = status
        if not pages:
            return result
        if detection := readers.detect_type(pages):
            if status == "ocr":
                detection["method"] = "ocr_title"
            result["detection"] = detection
        if reader := readers.READER_FOR_TYPE.get(result["detection"].get("code")):
            parsed = readers.read(pages, reader)
            header = readers.shipment_fields(pages)
            header.update({name: value for name, value in parsed.header.items() if value.status == Status.OK})
            _collect(result, header, reader)
            if reader == readers.PERMIT and len(pages) > 1:
                for page in pages:
                    other = {}
                    _collect(other, readers.read_fields([page], reader).header, reader)
                    result["references"].extend(ref for ref in other["references"] if ref not in result["references"])
    except adapters.ExtractionFailure as exc:
        result["reading_status"] = {
            "DOCUMENT_PROTECTED": "protected",
            "OCR_UNAVAILABLE": "ocr_unavailable",
            "PAGE_LIMIT": "page_limit",
        }.get(exc.code, "failed")
    except Exception:
        logger.info("Intake reading skipped for document %s", document.id, exc_info=True)
        result["reading_status"] = "failed"
    return result


def _collect(result, header, reader):
    values = {name: str(v.raw).strip() for name, v in header.items() if v.status == Status.OK and v.raw}
    result["party"] = values.get(PARTY.get(reader, "consignee"), "")
    refs = (*REFERENCES.get(reader, CITED), ("container", "container", "cited"))
    result["references"] = [
        {"kind": kind, "value": values[field], "role": role} for field, kind, role in refs if values.get(field)
    ]
    result["shipment"] = {field: values[field] for field in SHIPMENT_FIELDS if values.get(field)}
    if reader == readers.INVOICE and values.get("supplier_name"):
        result["shipment"].setdefault("shipper", values["supplier_name"])


def analyze(document: Document, *, allow_ocr=False) -> dict:
    """Les anciens dépôts restent analysables. L'OCR est borné et lancé au dépôt, hors du graphe."""
    analysis = document.intake_analysis
    if not analysis or (allow_ocr and analysis["reading_status"] in {"ocr_unavailable", "ocr_failed", "ocr_required"}):
        analysis = _preview(document, allow_ocr=allow_ocr)
        if analysis["reading_status"] != "ocr_required":
            document.intake_analysis = analysis
            document.save(update_fields=["intake_analysis"])
    detection = analysis["detection"]
    status = analysis["reading_status"]
    return {
        "party": analysis["party"],
        "references": analysis["references"],
        "shipment": analysis["shipment"],
        "reading_status": status,
        "document_id": str(document.id),
        "name": document.original_name,
        "type": detection.get("code", ""),
        "type_source": detection.get("method", ""),
        "read": status in {"native", "ocr"},
    }
