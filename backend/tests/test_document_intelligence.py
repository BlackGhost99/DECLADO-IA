"""Intelligence documentaire : associations multiples, garde-fous, décisions humaines."""

from collections import defaultdict

import pytest

from apps.cases.models import CaseDocument, CaseRevision, CustomsCase, Invoice
from apps.core.exceptions import ApiError
from apps.document_graph import intelligence
from apps.document_graph.models import DocumentConflict, DocumentInvoiceLink, Shipment, ShipmentDocument, ShipmentInvoice
from apps.documents.models import Document


def revision_for(org, user, reference):
    case = CustomsCase.objects.create(organization=org, reference=reference, created_by=user)
    return CaseRevision.objects.create(organization=org, case=case, revision_no=1, mode="demo", created_by=user)


def link_for(org, user, revision, name):
    document = Document.objects.create(
        organization=org,
        object_key="graph-tests/" + str(revision.id) + "/" + name,
        original_name=name,
        mime="application/pdf",
        bytes=20,
        sha256="1" * 64,
        uploaded_by=user,
    )
    return CaseDocument.objects.create(organization=org, revision=revision, document=document, added_by=user)


def refs(rows):
    index = defaultdict(dict)
    for kind, value, document in rows:
        index[(kind, value)][str(document.id)] = {
            "kind": kind, "value": value, "method": intelligence.ENGINE_VERSION
        }
    return index


@pytest.mark.django_db
def test_80_document_scenario_preserves_shared_many_to_many_and_idempotence(world, monkeypatch):
    org, user = world["org_a"], world["users"]["a_declarant"]
    revision = revision_for(org, user, "INTELLIGENCE-80")
    docs = [link_for(org, user, revision, "piece-%02d.pdf" % index) for index in range(80)]
    invoices = [
        Invoice.objects.create(
            organization=org, revision=revision, ordinal=i + 1,
            invoice_number="INV-%04d" % (i + 1), document=docs[i],
        )
        for i in range(10)
    ]
    rows = [
        ("transport", "BL-0012", docs[0]),
        ("transport", "BL-0012", docs[1]),
        ("transport", "BL-0012", docs[10]),
        ("invoice", "INV-0001", docs[10]),
        ("invoice", "INV-0002", docs[10]),
    ]
    monkeypatch.setattr(intelligence, "_reference_index", lambda *_: (refs(rows), {}))
    result = intelligence.analyze(org=org, actor=user, revision_id=revision.id)
    assert result["shipments"] == 1
    assert result["shipment_documents"] == 3
    assert result["shipment_invoices"] == 2
    assert result["document_invoices"] == 2
    assert Shipment.objects.count() == 1
    assert ShipmentDocument.objects.count() == 3
    assert ShipmentInvoice.objects.count() == 2
    assert DocumentInvoiceLink.objects.filter(document=docs[10]).count() == 2
    assert intelligence.analyze(org=org, actor=user, revision_id=revision.id) == {
        "document_invoices": 0, "shipments": 0, "shipment_documents": 0, "shipment_invoices": 0,
        "conflicts": 0,
    }
    links = list(ShipmentInvoice.objects.all())
    assert all(link.status == "proposed" for link in links)
    assert all(invoice.invoice_number.startswith("INV-") for invoice in invoices)
    shipment = Shipment.objects.get()
    with pytest.raises(ApiError):
        intelligence.confirm_shipment(org=org, actor=user, shipment_id=shipment.id)
    first = ShipmentDocument.objects.first()
    intelligence.review(org=org, actor=user, model="shipment_document", link_id=first.id, status="confirmed")
    intelligence.confirm_shipment(org=org, actor=user, shipment_id=shipment.id)
    assert Shipment.objects.get().status == "confirmed"


@pytest.mark.django_db
def test_wrong_tenant_invoice_link_never_crosses_revisions(world):
    a, b = world["org_a"], world["org_b"]
    ua, ub = world["users"]["a_declarant"], world["users"]["b_declarant"]
    ra, rb = revision_for(a, ua, "A-INT"), revision_for(b, ub, "B-INT")
    da = link_for(a, ua, ra, "a.pdf")
    ib = Invoice.objects.create(organization=b, revision=rb, ordinal=1, invoice_number="INV-1010")
    with pytest.raises(ApiError) as error:
        intelligence.create_invoice_link(
            org=a, actor=ua, revision_id=ra.id, document_id=da.id,
            invoice_id=ib.id, kind="insurance",
        )
    assert error.value.code == "NOT_FOUND"
    assert not DocumentInvoiceLink.objects.exists()


@pytest.mark.django_db
def test_conflict_resolution_is_attributed_and_does_not_change_invoice(world, monkeypatch):
    org, user = world["org_a"], world["users"]["a_declarant"]
    rev = revision_for(org, user, "CONFLICT-INT")
    doc = link_for(org, user, rev, "invoice.pdf")
    invoice = Invoice.objects.create(
        organization=org, revision=rev, ordinal=1,
        invoice_number="INV-2026-01", document=doc,
    )
    monkeypatch.setattr(
        intelligence, "_reference_index",
        lambda *_: (refs([]), {str(doc.id): {"INV-2026-02"}}),
    )
    result = intelligence.analyze(org=org, actor=user, revision_id=rev.id)
    assert result["conflicts"] == 1
    conflict = DocumentConflict.objects.get()
    assert conflict.status == "open"
    with pytest.raises(ApiError):
        intelligence.resolve_conflict(org=org, actor=user, conflict_id=conflict.id, reason="")
    intelligence.resolve_conflict(org=org, actor=user, conflict_id=conflict.id, reason="Vérifié sur l'original")
    assert DocumentConflict.objects.get().resolved_by_id == user.id
    assert Invoice.objects.get(pk=invoice.pk).invoice_number == "INV-2026-01"
    assert intelligence.analyze(org=org, actor=user, revision_id=rev.id)["conflicts"] == 0


@pytest.mark.django_db
def test_manual_shared_insurance_and_review_are_append_only(world):
    org, user = world["org_a"], world["users"]["a_declarant"]
    revision = revision_for(org, user, "INSURANCE-INT")
    document = link_for(org, user, revision, "insurance.pdf")
    invoices = [
        Invoice.objects.create(organization=org, revision=revision, ordinal=n, invoice_number="F-" + str(n))
        for n in (1, 2)
    ]
    for invoice in invoices:
        intelligence.create_invoice_link(
            org=org, actor=user, revision_id=revision.id,
            document_id=document.id, invoice_id=invoice.id, kind="insurance",
        )
    assert DocumentInvoiceLink.objects.filter(document=document, status="confirmed").count() == 2
    with pytest.raises(ApiError):
        intelligence.create_invoice_link(
            org=org, actor=user, revision_id=revision.id,
            document_id=document.id, invoice_id=invoices[0].id, kind="insurance",
        )


@pytest.mark.django_db
def test_document_intelligence_endpoint_is_tenant_scoped(world, session):
    a, b = world["org_a"], world["org_b"]
    ua, ub = world["users"]["a_declarant"], world["users"]["b_declarant"]
    ra, rb = revision_for(a, ua, "API-A-INT"), revision_for(b, ub, "API-B-INT")
    sa = session(ua.email)
    url_a = "/api/v1/revisions/" + str(ra.id) + "/document-intelligence"
    url_b = "/api/v1/revisions/" + str(rb.id) + "/document-intelligence"
    response = sa.get(url_a)
    assert response.status_code == 200, response.content
    assert response.json()["shipments"] == []
    assert sa.get(url_b).status_code == 404
    assert sa.post(url_b).status_code == 404
    assert sa.post(url_a).status_code == 200
    sb = session(ub.email)
    assert sb.get(url_a).status_code == 404
