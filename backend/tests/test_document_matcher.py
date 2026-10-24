from apps.document_graph.matcher import propose_links, references


def test_extract_references():
    result = references("Invoice No: INV-2026-012 | Bill of Lading: BL-2040-88")
    assert ("invoice", "INV-2026-012") in {(r["kind"], r["value"]) for r in result}


def test_many_to_many_associations():
    docs = [
        {"id": "bl", "text": "Bill of Lading No: BL-2026-01 invoice INV-0012 invoice INV-0013"},
        {"id": "a", "text": "Invoice No INV-0012 B/L BL-2026-01"},
        {"id": "b", "text": "Invoice No INV-0013 B/L BL-2026-01"},
    ]
    results = propose_links(docs)
    assert len(results) == 3
    assert all(result["status"] == "proposed" for result in results)


def test_no_link_without_identical_reference():
    docs = [
        {"id": "a", "text": "Invoice INV-2026-01"},
        {"id": "b", "text": "Invoice INV-2026-02"},
    ]
    assert propose_links(docs) == []


def test_numeric_only_text_is_not_reference():
    assert references("100 200 25000 XAF") == []
