"""Conservative document-type suggestions. Filename evidence is never legal validation."""

import re
import unicodedata

PATTERNS = (
    ("bill_of_lading", r"\b(bill.of.lading|connaissement|b[./ _-]?l)\b"),
    ("air_waybill", r"\b(air.waybill|lta|awb)\b"),
    ("road_consignment_note", r"\b(lettre.de.voiture|cmr)\b"),
    ("insurance_invoice", r"\b(facture.d?.?assurance|insurance.invoice)\b"),
    ("insurance_certificate", r"\b(?<!facture.)(?<!facture.d.)(assurance|insurance(?!.invoice)|police.assurance)\b"),
    ("freight_invoice", r"\b(fret|freight|transport.invoice|facture.transport)\b"),
    ("packing_list", r"\b(packing.list|liste.de.colisage)\b"),
    ("certificate_of_origin", r"\b(certificat.d.origine|certificate.of.origin)\b"),
    ("commercial_invoice", r"\b(facture.commerciale|commercial.invoice)\b"),
)


def suggest_document_type(filename: str) -> dict:
    normalized = unicodedata.normalize("NFKD", filename.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-z0-9]+", ".", normalized)
    hits = [code for code, pattern in PATTERNS if re.search(pattern, normalized)]
    return {
        "suggested_type": hits[0] if len(hits) == 1 else None,
        "status": "suggested_unverified" if len(hits) == 1 else "manual_review",
        "evidence": "filename_only",
        "confidence": "low",
        "matches": hits,
    }
