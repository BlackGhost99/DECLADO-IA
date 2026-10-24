"""Conservative reference matching across documents.

This module produces proposals only. It never validates associations or alters
source files, invoices, tariff classifications, or regulatory evidence.
"""
import re
from collections import defaultdict

PATTERNS = {
    "invoice": re.compile(
        r"\b(?:invoice|facture|factura)\s*(?:no\.?|n[°o]\.?|number|num(?:ero|éro)?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{3,29})",
        re.IGNORECASE,
    ),
    "transport": re.compile(
        r"\b(?:B/L|bill\s+of\s+lading|connaissement|awb|air\s+waybill)\s*(?:no\.?|n[°o]\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{3,29})",
        re.IGNORECASE,
    ),
    "purchase_order": re.compile(
        r"\b(?:P/O|purchase\s+order|bon\s+de\s+commande|pedido)\s*(?:no\.?|n[°o]\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{3,29})",
        re.IGNORECASE,
    ),
    "insurance": re.compile(
        r"\b(?:insurance\s+(?:policy|certificate)|police\s+d.assurance|seguro)\s*(?:no\.?|n[°o]\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{3,29})",
        re.IGNORECASE,
    ),
}


def references(text):
    """Return unique normalized references with source snippets only."""
    found = []
    seen = set()
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(text[:100000]):
            value = match.group(1).upper().strip("/-")
            if len(value) < 4 or not any(char.isdigit() for char in value):
                continue
            key = (kind, value)
            if key not in seen:
                seen.add(key)
                found.append({"kind": kind, "value": value, "excerpt": text[max(0, match.start()-20):match.end()+20][:160]})
    return found


def propose_links(documents):
    """documents: [{id, text}]; exact cross-document reference evidence only.

    A matched reference yields a candidate pair. No similarity-only automatic
    acceptance; a single reference may link many invoices or shipments.
    """
    index = defaultdict(list)
    for document in documents:
        for ref in references(document["text"]):
            index[(ref["kind"], ref["value"])].append((str(document["id"]), ref["excerpt"]))
    proposals = {}
    for (kind, value), occurrences in index.items():
        unique = {doc_id: snippet for doc_id, snippet in occurrences}
        if len(unique) < 2:
            continue
        ids = sorted(unique)
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                key = (left, right)
                proposals.setdefault(key, []).append({
                    "reference_kind": kind, "reference_value": value,
                    "source_excerpt": unique[left], "target_excerpt": unique[right],
                })
    return [
        {"source_id": source, "target_id": target, "status": "proposed",
         "evidence": evidence, "method": "exact-reference-v1"}
        for (source, target), evidence in sorted(proposals.items())
    ]
