"""Graph guarantees: shared documents, human confirmation and tenant isolation."""
import pytest
from apps.cases.models import CustomsCase, CaseRevision, CaseDocument
from apps.documents.models import Document
from apps.document_graph.services import add_relation
from apps.document_graph.models import DocumentRelation
from apps.core.exceptions import ApiError


def make_revision(org, user, ref):
    case = CustomsCase.objects.create(organization=org, reference=ref, created_by=user)
    return CaseRevision.objects.create(
        organization=org, case=case, revision_no=1, mode="demo", created_by=user
    )


def make_link(org, user, revision, name):
    doc = Document.objects.create(
        organization=org, object_key=f"test/{org.pk}/{name}",
        original_name=name, mime="application/pdf", bytes=10, sha256="a" * 64,
        uploaded_by=user,
    )
    return CaseDocument.objects.create(
        organization=org, revision=revision, document=doc, added_by=user
    )


@pytest.mark.django_db
def test_shared_transport_links_multiple_invoices(world):
    org = world["org_a"]
    user = world["users"]["a_declarant"]
    revision = make_revision(org, user, "GRAPH-001")
    transport = make_link(org, user, revision, "bl.pdf")
    inv_a = make_link(org, user, revision, "invoice-a.pdf")
    inv_b = make_link(org, user, revision, "invoice-b.pdf")
    for invoice in (inv_a, inv_b):
        add_relation(org=org, actor=user, revision_id=revision.pk,
                     source_id=transport.pk, target_id=invoice.pk, kind="shared_transport")
    assert DocumentRelation.objects.for_organization(org).filter(source=transport).count() == 2


@pytest.mark.django_db
def test_cross_tenant_document_is_rejected(world):
    a, b = world["org_a"], world["org_b"]
    user_a, user_b = world["users"]["a_declarant"], world["users"]["b_declarant"]
    rev_a = make_revision(a, user_a, "GRAPH-A")
    rev_b = make_revision(b, user_b, "GRAPH-B")
    doc_a = make_link(a, user_a, rev_a, "a.pdf")
    doc_b = make_link(b, user_b, rev_b, "b.pdf")
    with pytest.raises(ApiError):
        add_relation(org=a, actor=user_a, revision_id=rev_a.pk,
                     source_id=doc_a.pk, target_id=doc_b.pk, kind="same_shipment")
    assert not DocumentRelation.objects.exists()


@pytest.mark.django_db
def test_duplicate_relation_is_rejected(world):
    org, user = world["org_a"], world["users"]["a_declarant"]
    rev = make_revision(org, user, "GRAPH-DUP")
    left = make_link(org, user, rev, "a.pdf")
    right = make_link(org, user, rev, "b.pdf")
    args = dict(org=org, actor=user, revision_id=rev.pk,
                source_id=left.pk, target_id=right.pk, kind="same_shipment")
    add_relation(**args)
    with pytest.raises(ApiError):
        add_relation(**args)
