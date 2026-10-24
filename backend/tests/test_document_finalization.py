"""Security and conservative classification contract for documentary V1."""

from uuid import UUID

import pytest
from django.urls import resolve

from apps.regulations.api import (
    CaseDocumentChecklistView,
    DocumentTypeListView,
    OrganizationDocumentPolicyView,
)
from apps.regulations.classification import suggest_document_type


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("facture-fret.pdf", "freight_invoice"),
        ("attestation_assurance.png", "insurance_certificate"),
        ("B-L-001.pdf", "bill_of_lading"),
        ("lettre-de-transport-lta.pdf", "air_waybill"),
        ("commercial_invoice_42.pdf", "commercial_invoice"),
    ],
)
def test_suggestions_are_unverified(filename, expected):
    result = suggest_document_type(filename)
    assert result["suggested_type"] == expected
    assert result["confidence"] == "low"
    assert result["status"] == "suggested_unverified"


def test_unknown_is_never_accepted_as_proof():
    result = suggest_document_type("scan1234.pdf")
    assert result["suggested_type"] is None
    assert result["status"] == "manual_review"


def test_api_routes():
    revision_id = UUID("00000000-0000-0000-0000-000000000001")
    assert resolve(f"/api/v1/revisions/{revision_id}/document-checklist").func.view_class is CaseDocumentChecklistView
    assert resolve("/api/v1/document-types").func.view_class is DocumentTypeListView
    assert resolve("/api/v1/organization/document-policies").func.view_class is OrganizationDocumentPolicyView


@pytest.mark.django_db
def test_policy_not_anonymous(client):
    response = client.post(
        "/api/v1/organization/document-policies",
        {"document_type": "commercial_invoice"},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_document_taxonomy_not_anonymous(client):
    assert client.get("/api/v1/document-types").status_code in (401, 403)
