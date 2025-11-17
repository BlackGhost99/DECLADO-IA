"""
Fixtures pytest communes pour DECLADO-IA Backend
Phase 10: Tests, QA et Performance
"""

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app as fastapi_app

# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def test_db_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a test database session."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(test_db_session):
    """Create FastAPI test client with test database."""

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


# ============================================================================
# Data Fixtures
# ============================================================================


@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing."""
    return {
        "invoice_number": "FAC-2025-001",
        "date": "2025-01-15",
        "vendor": "Test Supplier Ltd",
        "total": 10000.00,
        "currency": "USD",
    }


@pytest.fixture
def sample_calculation_input():
    """Sample customs calculation input."""
    return {
        "invoice_number": "INV-TEST-001",
        "hs_code": "6109",
        "description": "T-shirts en coton",
        "quantity": Decimal("100"),
        "unit_price": Decimal("5.50"),
        "currency": "EUR",
        "incoterm": "CIF",
        "origin_country": "CN",
        "destination_country": "CM",
        "freight_cost": Decimal("200.00"),
        "insurance_cost": Decimal("50.00"),
        "exchange_rate": Decimal("655.957"),
    }


@pytest.fixture
def sample_hs_classification():
    """Sample HS classification data."""
    return {
        "product_description": "T-shirt 100% coton, col rond, manches courtes",
        "suggested_codes": [
            {"code": "6109.10", "confidence": 0.92, "description": "T-shirts de coton"},
            {"code": "6109.90", "confidence": 0.75, "description": "T-shirts autres matières"},
        ],
    }


# ============================================================================
# File Fixtures
# ============================================================================


@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        # Create minimal PDF (empty for now - could use reportlab if needed)
        tmp.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        tmp_path = tmp.name

    yield tmp_path

    # Cleanup
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def temp_image_file():
    """Create a temporary image file with test content."""
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "FACTURE TEST-001", fill=(0, 0, 0))
    draw.text((10, 40), "Montant: 1234.56 EUR", fill=(0, 0, 0))
    draw.text((10, 70), "Client: Test Corp", fill=(0, 0, 0))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp, format="PNG")
        tmp_path = tmp.name

    yield tmp_path

    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def temp_csv_file():
    """Create a temporary CSV file with batch test data."""
    content = """invoice_number,hs_code,description,quantity,unit_price,currency
INV-001,6109,T-shirt coton,100,5.50,EUR
INV-002,8517,Smartphone,50,250.00,USD
INV-003,6204,Robe femme,75,35.00,EUR
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    yield tmp_path

    if os.path.exists(tmp_path):
        os.remove(tmp_path)


# ============================================================================
# Performance Fixtures
# ============================================================================


@pytest.fixture
def performance_logger():
    """Logger for performance metrics."""
    import time

    class PerfLogger:
        def __init__(self):
            self.metrics = {}

        def start(self, name: str):
            self.metrics[name] = {"start": time.perf_counter()}

        def end(self, name: str):
            if name in self.metrics:
                self.metrics[name]["end"] = time.perf_counter()
                self.metrics[name]["duration"] = (
                    self.metrics[name]["end"] - self.metrics[name]["start"]
                )

        def get_duration(self, name: str) -> float:
            return self.metrics.get(name, {}).get("duration", 0.0)

        def report(self):
            for name, data in self.metrics.items():
                duration = data.get("duration", 0)
                print(f"⏱️  {name}: {duration*1000:.2f}ms")

    return PerfLogger()


# ============================================================================
# ML Fixtures
# ============================================================================


@pytest.fixture
def mock_ml_model(tmp_path):
    """Create a mock ML model for testing."""
    from app.ml.config import MODEL_DIR

    # Ensure model directory exists
    os.makedirs(MODEL_DIR, exist_ok=True)

    # Create dummy ONNX model file
    model_path = Path(MODEL_DIR) / "test_classifier.onnx"
    model_path.write_bytes(b"MOCK_ONNX_MODEL")

    yield str(model_path)

    # Cleanup
    if model_path.exists():
        model_path.unlink()


@pytest.fixture
def sample_training_data(tmp_path):
    """Create sample CSV training data."""
    csv_content = """hs_code,description
6109,T-shirt en coton
6204,Robe pour femme
8517,Téléphone portable
6403,Chaussures en cuir
"""
    csv_path = tmp_path / "training_data.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    return str(csv_path)
