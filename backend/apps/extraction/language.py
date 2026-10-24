"""Deterministic document language hints; no translation and no legal classification.

The result is intentionally conservative. Mixed/unknown documents remain reviewable.
"""
import re
import unicodedata
from collections import Counter

VOCABULARY = {
    "fr": {"facture", "fournisseur", "désignation", "quantité", "montant", "marchandise", "assurance", "livraison"},
    "en": {"invoice", "supplier", "description", "quantity", "amount", "freight", "insurance", "shipping"},
    "es": {"factura", "proveedor", "descripción", "cantidad", "importe", "mercancía", "seguro", "envío"},
}
ARABIC = re.compile(r"[\u0600-\u06ff]")
TOKENS = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str) -> dict:
    """Return a conservative language hint and evidence counts; never claim calibrated probability."""
    sample = text[:30000]
    words = [w.casefold() for w in TOKENS.findall(sample)]
    counts = Counter(words)
    scores = {lang: sum(counts[word] for word in vocab) for lang, vocab in VOCABULARY.items()}
    arabic_words = sum(1 for word in words if ARABIC.search(word))
    if arabic_words >= 3:
        scores["ar"] = arabic_words
    else:
        scores["ar"] = 0
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, runner_up = ordered[0], ordered[1]
    evidence = sum(scores.values())
    # Require two independent lexical clues and a clear margin; ties are unknown.
    independent = sum(1 for word in set(words) if word in VOCABULARY.get(best[0], set()))
    if best[0] == "ar":
        independent = len(set(w for w in words if ARABIC.search(w)))
    known = best[1] >= 3 and independent >= 2 and best[1] >= runner_up[1] + 2
    return {
        "locale": best[0] if known else "",
        "status": "detected" if known else ("ambiguous" if evidence else "unknown"),
        "method": "lexical-v1",
        "scores": scores,
        "evidence_count": evidence,
        "sample_characters": len(sample),
        "confidence": None,
    }


def annotate_parsed(doc, pages) -> None:
    """Metadata only; original strings and normalized customs values remain untouched."""
    text = "\n".join(row.text for page in pages for row in page.rows)
    doc.stats["language_detection"] = detect_language(text)
