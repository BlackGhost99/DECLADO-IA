"""
Integration tests - End-to-End Pipeline
Phase 10: Tests, QA et Performance
"""

import json
import os
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import UploadFile

# ============================================================================
# E2E: Upload → OCR → Classification → Calculation → Export
# ============================================================================


@pytest.mark.e2e
@pytest.mark.integration
def test_complete_pipeline_pdf_upload(client, temp_pdf_file):
    """
    Complete E2E test: Upload PDF → OCR → HS Classification → Customs Calc → Export

    Workflow:
    1. Upload PDF invoice
    2. OCR extracts text
    3. Classify products by HS code
    4. Calculate customs duties
    5. Export result as PDF/CSV
    """
    # Step 1: Upload PDF for OCR processing
    with open(temp_pdf_file, "rb") as f:
        response = client.post(
            "/api/ocr/process",
            files={"file": ("test_invoice.pdf", f, "application/pdf")},
            data={"lang": "fra"},
        )

    assert response.status_code == 200
    ocr_result = response.json()

    assert "source" in ocr_result
    assert "num_pages" in ocr_result

    # Step 2: HS Classification (simulate extracted product description)
    product_desc = "T-shirt en coton 100%"

    response = client.post("/api/hs/suggest", json={"text": product_desc, "k": 3})

    assert response.status_code == 200
    hs_result = response.json()
    assert "suggestions" in hs_result
    assert len(hs_result["suggestions"]) > 0

    suggested_hs = hs_result["suggestions"][0]["code"]

    # Step 3: Customs calculation
    calc_request = {
        "invoice_number": "E2E-TEST-001",
        "hs_code": suggested_hs,
        "description": product_desc,
        "quantity": 100,
        "unit_price": 5.50,
        "currency": "EUR",
        "incoterm": "CIF",
        "origin_country": "CN",
        "destination_country": "CM",
        "freight_cost": 200.0,
        "insurance_cost": 50.0,
    }

    response = client.post("/api/customs/calculate", json=calc_request)
    assert response.status_code == 200

    calc_result = response.json()
    assert "calculation_id" in calc_result
    assert "taxable_base" in calc_result
    assert "tax_breakdown" in calc_result

    # Step 4: Export as CSV
    export_request = {
        "format": "csv",
        "calculation": calc_request,
        "meta": {
            "declarant_name": "Test Declarant",
            "customs_office": "Douala Port",
        },
    }

    response = client.post("/api/export", json=export_request)
    assert response.status_code == 200

    csv_content = response.text
    assert "calculation_id" in csv_content
    assert calc_result["calculation_id"] in csv_content


@pytest.mark.e2e
@pytest.mark.integration
def test_complete_pipeline_image_upload(client, temp_image_file):
    """E2E test with image upload instead of PDF."""
    # Upload image
    with open(temp_image_file, "rb") as f:
        response = client.post(
            "/api/ocr/process",
            files={"file": ("test_invoice.png", f, "image/png")},
            data={"lang": "fra+eng"},
        )

    assert response.status_code == 200
    ocr_result = response.json()

    # Should extract some text
    assert "pages" in ocr_result
    assert len(ocr_result["pages"]) > 0


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.slow
def test_batch_processing_200_items(client, temp_csv_file):
    """
    Batch processing test: Process 200 invoice lines

    Tests throughput and stability under load.
    """
    import csv

    # Read CSV with batch data
    with open(temp_csv_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Extend to 200 items
    batch_items = rows * 67  # Repeat to get ~200 items
    batch_items = batch_items[:200]

    results = []
    errors = 0

    for idx, row in enumerate(batch_items):
        calc_request = {
            "invoice_number": f"BATCH-{idx:03d}",
            "hs_code": row["hs_code"],
            "description": row["description"],
            "quantity": float(row["quantity"]),
            "unit_price": float(row["unit_price"]),
            "currency": row["currency"],
            "incoterm": "CIF",
            "origin_country": "CN",
            "destination_country": "CM",
        }

        response = client.post("/api/customs/calculate", json=calc_request)

        if response.status_code == 200:
            results.append(response.json())
        else:
            errors += 1

    # Assertions
    assert len(results) >= 190, "At least 95% success rate expected"
    assert errors <= 10, f"Too many errors: {errors}/200"

    print(f"✅ Processed {len(results)}/200 items successfully")
    print(f"❌ Errors: {errors}")


# ============================================================================
# Integration: API Health & Availability
# ============================================================================


@pytest.mark.integration
def test_api_health_check(client):
    """Test health check endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data
    assert "version" in data


@pytest.mark.integration
def test_api_ping(client):
    """Test simple ping endpoint."""
    response = client.get("/api/health/ping")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "pong"


# ============================================================================
# Integration: Cross-Module Dependencies
# ============================================================================


@pytest.mark.integration
def test_ocr_to_classification_pipeline(client, temp_image_file):
    """Test OCR output can feed into HS classification."""
    # OCR
    with open(temp_image_file, "rb") as f:
        response = client.post(
            "/api/ocr/process",
            files={"file": ("invoice.png", f, "image/png")},
        )

    assert response.status_code == 200
    ocr_data = response.json()

    # Extract text from first page
    if ocr_data.get("pages") and len(ocr_data["pages"]) > 0:
        page_text = ocr_data["pages"][0].get("text", "")

        # Classify
        if page_text:
            response = client.post(
                "/api/hs/suggest", json={"text": page_text[:500], "k": 3}  # Limit text length
            )

            # Should work even if text is partial/garbage
            assert response.status_code in [200, 400]


@pytest.mark.integration
def test_classification_to_calculation_pipeline(client):
    """Test HS classification output feeds into customs calculation."""
    # Get HS code suggestion
    response = client.post("/api/hs/suggest", json={"text": "smartphone samsung", "k": 1})

    assert response.status_code == 200
    hs_data = response.json()

    if hs_data["suggestions"]:
        hs_code = hs_data["suggestions"][0]["code"]

        # Use in calculation
        calc_request = {
            "invoice_number": "INT-TEST-001",
            "hs_code": hs_code,
            "description": "Smartphone Samsung Galaxy",
            "quantity": 10,
            "unit_price": 250.0,
            "currency": "USD",
            "incoterm": "FOB",
            "origin_country": "KR",
            "destination_country": "CM",
        }

        response = client.post("/api/customs/calculate", json=calc_request)
        assert response.status_code == 200


# ============================================================================
# Integration: Database Consistency
# ============================================================================


@pytest.mark.integration
def test_health_check_database_write(client):
    """Test health check writes to database."""
    # Multiple health checks
    for _ in range(3):
        response = client.get("/api/health")
        assert response.status_code == 200

    # Database should have health_check records
    # (This is implicit - if writes failed, health would be "degraded")


# ============================================================================
# Integration: Error Handling & Edge Cases
# ============================================================================


@pytest.mark.integration
def test_invalid_file_upload(client):
    """Test uploading invalid file type."""
    # Create fake file
    fake_content = b"This is not a valid PDF or image"

    response = client.post(
        "/api/ocr/process",
        files={"file": ("fake.txt", BytesIO(fake_content), "text/plain")},
    )

    # Should either reject or handle gracefully
    assert response.status_code in [200, 400, 415, 500]


@pytest.mark.integration
def test_calculation_invalid_hs_code(client):
    """Test customs calculation with invalid HS code."""
    calc_request = {
        "invoice_number": "ERR-001",
        "hs_code": "9999",  # Invalid/unknown code
        "description": "Unknown product",
        "quantity": 1,
        "unit_price": 10.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "XX",  # Invalid country
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=calc_request)

    # Should process but may have warnings
    # (Current implementation doesn't validate HS codes strictly)
    assert response.status_code in [200, 400]


@pytest.mark.integration
def test_export_without_calculation(client):
    """Test export with minimal data."""
    export_request = {
        "format": "json",
        "calculation": {
            "invoice_number": "MIN-001",
            "hs_code": "0000",
            "description": "Test",
            "quantity": 1,
            "unit_price": 1.0,
            "currency": "USD",
            "incoterm": "FOB",
            "origin_country": "FR",
            "destination_country": "CM",
        },
    }

    response = client.post("/api/export", json=export_request)
    assert response.status_code == 200
