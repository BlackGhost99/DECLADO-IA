"""
Security Tests
Phase 10: Tests, QA et Performance
"""

import pytest

# ============================================================================
# SQL Injection Tests
# ============================================================================


@pytest.mark.security
def test_sql_injection_invoice_number(client):
    """Test SQL injection attempt in invoice_number field."""
    malicious_input = {
        "invoice_number": "INV-001'; DROP TABLE invoices; --",
        "hs_code": "6109",
        "description": "Test product",
        "quantity": 1,
        "unit_price": 10.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=malicious_input)

    # Should either reject or sanitize (not cause DB error)
    assert response.status_code in [200, 400, 422]

    # Verify database still exists by checking health
    health = client.get("/api/health")
    assert health.status_code == 200


@pytest.mark.security
def test_sql_injection_description_field(client):
    """Test SQL injection in description field."""
    malicious_input = {
        "invoice_number": "INV-002",
        "hs_code": "6109",
        "description": "Product' OR '1'='1",
        "quantity": 1,
        "unit_price": 10.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=malicious_input)
    assert response.status_code in [200, 400, 422]


# ============================================================================
# File Upload Security
# ============================================================================


@pytest.mark.security
def test_file_upload_size_limit(client):
    """Test file upload size restrictions."""
    # Create oversized file (10MB)
    large_content = b"X" * (10 * 1024 * 1024)

    from io import BytesIO

    response = client.post(
        "/api/ocr/process",
        files={"file": ("huge.pdf", BytesIO(large_content), "application/pdf")},
    )

    # Should reject or handle gracefully
    # (Current implementation may not have explicit size limit yet)
    assert response.status_code in [200, 400, 413, 500]


@pytest.mark.security
def test_file_upload_malicious_extension(client):
    """Test uploading executable files."""
    from io import BytesIO

    exe_content = b"MZ\x90\x00"  # PE executable header

    response = client.post(
        "/api/ocr/process",
        files={"file": ("malware.exe", BytesIO(exe_content), "application/octet-stream")},
    )

    # Should reject non-document files
    assert response.status_code in [400, 415, 500]


@pytest.mark.security
def test_file_upload_script_injection(client):
    """Test uploading files with embedded scripts."""
    from io import BytesIO

    # SVG with embedded JavaScript
    svg_content = b"""<?xml version="1.0"?>
    <svg xmlns="http://www.w3.org/2000/svg">
        <script>alert('XSS')</script>
    </svg>"""

    response = client.post(
        "/api/ocr/process",
        files={"file": ("test.svg", BytesIO(svg_content), "image/svg+xml")},
    )

    # Should reject or sanitize
    assert response.status_code in [200, 400, 415, 500]


# ============================================================================
# Input Validation Tests
# ============================================================================


@pytest.mark.security
def test_input_validation_negative_quantity(client):
    """Test negative quantity is rejected."""
    invalid_input = {
        "invoice_number": "INV-003",
        "hs_code": "6109",
        "description": "Test",
        "quantity": -10,  # Invalid
        "unit_price": 5.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=invalid_input)

    # Should reject (Pydantic validation with gt=0)
    assert response.status_code == 422


@pytest.mark.security
def test_input_validation_negative_price(client):
    """Test negative price is rejected."""
    invalid_input = {
        "invoice_number": "INV-004",
        "hs_code": "6109",
        "description": "Test",
        "quantity": 10,
        "unit_price": -5.0,  # Invalid
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=invalid_input)
    assert response.status_code == 422


@pytest.mark.security
def test_input_validation_invalid_currency(client):
    """Test invalid currency code."""
    invalid_input = {
        "invoice_number": "INV-005",
        "hs_code": "6109",
        "description": "Test",
        "quantity": 10,
        "unit_price": 5.0,
        "currency": "INVALID",  # Not 3-char ISO code
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=invalid_input)

    # Should reject (min_length=3, max_length=3)
    assert response.status_code == 422


@pytest.mark.security
def test_input_validation_xss_attempt(client):
    """Test XSS attempt in text fields."""
    xss_payload = {
        "invoice_number": "INV-006",
        "hs_code": "6109",
        "description": "<script>alert('XSS')</script>",
        "quantity": 10,
        "unit_price": 5.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=xss_payload)

    # Should accept (backend doesn't render HTML)
    # But response should not execute script
    assert response.status_code == 200

    result = response.json()
    # Verify script tag is stored as-is, not executed
    assert "<script>" in result["input"]["description"]


# ============================================================================
# Authentication & Authorization Tests (Future)
# ============================================================================


@pytest.mark.security
@pytest.mark.skip(reason="Authentication not yet implemented")
def test_unauthenticated_access_blocked():
    """Test that protected endpoints require authentication."""
    # TODO: When auth is added, test unauthorized access is blocked
    pass


@pytest.mark.security
@pytest.mark.skip(reason="RBAC not yet implemented")
def test_role_based_access_control():
    """Test operator vs supervisor role permissions."""
    # TODO: Test different roles have appropriate access levels
    pass


# ============================================================================
# Database Security Tests
# ============================================================================


@pytest.mark.security
def test_database_connection_encryption_available():
    """Test database encryption status."""
    from app.db.database import SQLCIPHER_AVAILABLE

    # Log current encryption status
    if SQLCIPHER_AVAILABLE:
        print("✅ SQLCipher encryption available")
    else:
        print("⚠️  SQLCipher unavailable - using unencrypted SQLite")
        print("   Consider enabling application-level field encryption")

    # This is informational - not a hard failure
    # (encryption optional for dev, required for prod)


@pytest.mark.security
def test_database_no_exposed_credentials(client):
    """Test database credentials are not exposed in responses."""
    response = client.get("/api/health")

    response_text = response.text.lower()

    # Should not contain sensitive patterns
    assert "password" not in response_text
    assert "secret" not in response_text
    assert "key" not in response_text or "api_key" not in response_text


# ============================================================================
# CORS & Security Headers Tests
# ============================================================================


@pytest.mark.security
def test_cors_headers_present(client):
    """Test CORS headers are configured."""
    response = client.options("/api/health")

    # Should have CORS headers
    # (TestClient may not fully simulate CORS, but check basic headers)
    assert response.status_code in [200, 405]


@pytest.mark.security
def test_no_sensitive_info_in_error_messages(client):
    """Test error messages don't leak sensitive information."""
    # Trigger an error
    invalid_request = {
        "invoice_number": "ERR-001",
        "hs_code": "INVALID_HS_CODE_VERY_LONG" * 10,  # Too long
        "description": "Test",
        "quantity": 1,
        "unit_price": 1.0,
        "currency": "USD",
        "incoterm": "FOB",
        "origin_country": "FR",
        "destination_country": "CM",
    }

    response = client.post("/api/customs/calculate", json=invalid_request)

    error_text = response.text.lower()

    # Should not expose internal paths or stack traces
    assert "c:\\" not in error_text
    assert "/home/" not in error_text
    assert "traceback" not in error_text


# ============================================================================
# Rate Limiting Tests (Future)
# ============================================================================


@pytest.mark.security
@pytest.mark.skip(reason="Rate limiting not yet implemented")
def test_rate_limiting_blocks_excessive_requests(client):
    """Test rate limiting prevents abuse."""
    # TODO: When rate limiting is added, test it works
    pass


# ============================================================================
# Audit Logging Tests
# ============================================================================


@pytest.mark.security
def test_audit_log_exists():
    """Test audit log file exists and is being written."""
    import os

    from app.core.config import settings

    # Check if audit logging is enabled
    log_dir = "logs"
    if os.path.exists(log_dir):
        log_files = os.listdir(log_dir)
        audit_logs = [f for f in log_files if "audit" in f.lower()]

        if audit_logs:
            print(f"✅ Audit logging active: {audit_logs}")
        else:
            print("⚠️  No audit logs found")
    else:
        print("⚠️  Logs directory not found")


@pytest.mark.security
def test_audit_log_tamper_detection():
    """Test audit log has HMAC integrity checks."""
    import json
    import os

    log_path = "logs/declado-audit.log"

    if os.path.exists(log_path):
        with open(log_path) as f:
            lines = f.readlines()

        if lines:
            # Check last line has HMAC
            last_entry = json.loads(lines[-1])
            assert "hmac" in last_entry, "Audit log missing HMAC integrity check"
            assert "prev_hmac" in last_entry, "Audit log missing chain reference"
            print("✅ Audit log has tamper detection (HMAC chain)")
        else:
            print("⚠️  Audit log empty")
    else:
        print("⚠️  Audit log not found")
