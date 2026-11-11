from apps.cases.intake_grouping import group_shipments


def piece(name, *, party="Petro Services Gabon", invoice="", bl="", own="", shipment=None):
    refs = [
        {"kind": kind, "value": value, "role": "own" if kind == own else "cited"}
        for kind, value in (("invoice", invoice), ("bl", bl))
        if value
    ]
    return {
        "document_id": name,
        "name": name,
        "party": party,
        "references": refs,
        "shipment": shipment or {},
    }


CARGO = {"shipper": "Gabon Export SA", "packages": "12 colis", "gross_weight": "425,50 kg"}


def test_cargo_details_link_invoice_transport_and_supporting_documents_without_shared_references():
    docs = [
        piece("invoice", invoice="INV-01", own="invoice", shipment=CARGO),
        piece("transport", bl="BL-99", own="bl", shipment=CARGO),
        piece("packing", shipment={**CARGO, "gross_weight": "425.50 KGS"}),
        piece("insurance", shipment=CARGO),
        piece("other importer", party="Autre importateur", invoice="INV-02", own="invoice", shipment=CARGO),
        piece("party only"),
    ]
    result = group_shipments(docs)
    group = next(g for g in result["groups"] if g["party"] == "Petro Services Gabon")
    assert {d["name"] for d in group["documents"]} == {"invoice", "transport", "packing", "insurance"}
    assert group["confidence"] == "medium"
    assert group["context"] == "cargo_shipper"
    assert [d["name"] for d in result["unassigned"]] == ["party only"]
    assert len(result["groups"]) == 2


def test_multiple_same_importer_shipments_keep_ambiguous_attachment_out():
    result = group_shipments(
        [
            piece("invoice 1", invoice="INV-01", own="invoice", shipment=CARGO),
            piece("invoice 2", invoice="INV-02", own="invoice", shipment=CARGO),
            piece("packing", shipment=CARGO),
        ]
    )
    assert len(result["groups"]) == 2
    assert len({g["title"] for g in result["groups"]}) == 2
    assert all(len(g["documents"]) == 1 for g in result["groups"])
    assert result["unassigned"][0]["assignment_issue"] == "ambiguous"


def test_conflicting_bl_bridge_does_not_merge_two_invoices():
    result = group_shipments(
        [
            piece("invoice 1", invoice="INV-01", bl="BL-99", own="invoice"),
            piece("invoice 2", invoice="INV-02", bl="BL-99", own="invoice"),
            piece("permit", invoice="INV-01", bl="BL-99"),
        ]
    )
    assert len(result["groups"]) == 2
    assert all(g["confidence"] == "review" for g in result["groups"])
    assert result["unassigned"][0]["assignment_issue"] == "ambiguous"


def test_identical_invoice_reference_cannot_merge_different_importers():
    result = group_shipments(
        [
            piece("invoice 1", invoice="INV-01", own="invoice"),
            piece("invoice 2", party="Autre importateur", invoice="INV-01", own="invoice"),
            piece("unsigned packing", party="", invoice="INV-01"),
        ]
    )
    assert len(result["groups"]) == 2
    assert [d["name"] for d in result["unassigned"]] == ["unsigned packing"]
