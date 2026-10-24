"""Document type hints from already extracted OCR/text spans; never automatic approval."""

import re
import unicodedata

# Prefer explicit document headings, not loose mentions within an invoice.
HEADINGS = {
    "bill_of_lading": (r"\bbill\s+of\s+lading\b", r"\bconnaissement\s+maritime\b"),
    "air_waybill": (r"\bair\s+waybill\b", r"\blettre\s+de\s+transport\s+aerien\b"),
    "road_consignment_note": (r"\bconsignment\s+note\b", r"\blettre\s+de\s+voiture\b"),
    "insurance_certificate": (r"\binsurance\s+certificate\b", r"\bcertificat\s+d.assurance\b"),
    "freight_invoice": (r"\bfreight\s+invoice\b", r"\bfacture\s+de\s+fret\b"),
    "packing_list": (r"\bpacking\s+list\b", r"\bliste\s+de\s+colisage\b"),
    "certificate_of_origin": (r"\bcertificate\s+of\s+origin\b", r"\bcertificat\s+d.origine\b"),
    "commercial_invoice": (r"\bcommercial\s+invoice\b", r"\bfacture\s+commerciale\b"),
}


def suggest_from_excerpts(excerpts: list[str]) -> dict:
    """Consider only bounded extracted text; ambiguous matches require manual review.

    The caller must supply excerpts from a document belonging to the active organization.
    No extracted business content is returned to clients.
    """
    hits = set()
    for excerpt in excerpts[:100]:
        if not isinstance(excerpt, str):
            continue
        text = unicodedata.normalize("NFKD", excerpt.lower())
        text = "".join(character for character in text if not unicodedata.combining(character))
        text = re.sub(r"\s+", " ", text[:500])
        for code, expressions in HEADINGS.items():
            if any(re.search(expression, text) for expression in expressions):
                hits.add(code)
    matches = sorted(hits)
    return {
        "suggested_type": matches[0] if len(matches) == 1 else None,
        "status": "suggested_unverified" if len(matches) == 1 else "manual_review",
        "evidence": "extracted_content" if excerpts else "none",
        "confidence": "low",
        "matches": matches,
        "review_required": True,
    }
