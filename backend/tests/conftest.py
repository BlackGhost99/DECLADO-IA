"""
Fixtures pytest communes
"""
import pytest


@pytest.fixture
def sample_invoice_data():
    """Données d'exemple d'une facture"""
    return {
        "invoice_number": "FAC-2025-001",
        "date": "2025-01-15",
        "vendor": "Test Supplier Ltd",
        "total": 10000.00,
        "currency": "USD"
    }
