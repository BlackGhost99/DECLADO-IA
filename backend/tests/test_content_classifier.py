"""OCR and extracted-text hints require an explicit human decision."""

from apps.regulations.content_classifier import suggest_from_excerpts


def test_shipping_document_heading():
    result = suggest_from_excerpts(["BILL OF LADING", "Ship name: Example"])
    assert result["suggested_type"] == "bill_of_lading"
    assert result["review_required"] is True
    assert result["evidence"] == "extracted_content"


def test_multi_document_text_is_ambiguous():
    result = suggest_from_excerpts(["COMMERCIAL INVOICE", "PACKING LIST"])
    assert result["suggested_type"] is None
    assert result["status"] == "manual_review"
    assert set(result["matches"]) == {"commercial_invoice", "packing_list"}


def test_empty_extraction_does_not_guess():
    result = suggest_from_excerpts([])
    assert result["suggested_type"] is None
    assert result["evidence"] == "none"


def test_accents_are_normalized():
    result = suggest_from_excerpts(["CERTIFICAT D’ORIGINE"])
    assert result["review_required"] is True
    assert result["suggested_type"] == "certificate_of_origin"


def test_raw_content_not_returned():
    secret = "Commercial invoice client-secret-123"
    result = suggest_from_excerpts([secret])
    assert "client-secret-123" not in str(result)
