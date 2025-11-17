"""
Unit Tests - Tariff Configuration Loading
Phase 10: Tests, QA et Performance
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.rules_engine.config import TariffConfig


# ============================================================================
# Configuration Loading Tests
# ============================================================================


@pytest.fixture
def temp_config_dir():
    """Create temporary directory with test config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create test TEC rates
        tec_data = {
            "rates": {
                "6109": 30,
                "6204": 25,
                "8517": 20,
                "default": 20,
            }
        }
        (config_dir / "cemac_tec.yaml").write_text(yaml.dump(tec_data), encoding="utf-8")

        # Create test VAT rates
        vat_data = {
            "rates": {
                "CM": 19.25,
                "GA": 18.0,
                "CEMAC": 19.25,
            }
        }
        (config_dir / "vat_rates.yaml").write_text(yaml.dump(vat_data), encoding="utf-8")

        # Create test exemptions
        exemptions_data = {
            "exemptions": {
                "EXO_MEDICAL": {
                    "dd_rate": 0,
                    "vat_rate": 0,
                    "description": "Exonération médicale",
                },
                "EXO_CEMAC": {
                    "dd_rate": 0,
                    "vat_rate": 19.25,
                    "description": "Exonération DD intra-CEMAC",
                },
            }
        }
        (config_dir / "exemptions.yaml").write_text(
            yaml.dump(exemptions_data), encoding="utf-8"
        )

        # Create test exchange rates
        exchange_data = {
            "rates": {
                "USD": 600,
                "EUR": 655.957,
                "GBP": 750,
                "default": 600,
            }
        }
        (config_dir / "exchange_rates.yaml").write_text(
            yaml.dump(exchange_data), encoding="utf-8"
        )

        yield config_dir


@pytest.mark.unit
def test_config_initialization(temp_config_dir):
    """Test TariffConfig initialization."""
    config = TariffConfig(temp_config_dir)

    assert config.data_dir == temp_config_dir
    assert config.tec_rates is not None
    assert config.vat_rates is not None


@pytest.mark.unit
def test_get_tec_rate_exact_match(temp_config_dir):
    """Test getting TEC rate with exact HS code match."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_tec_rate("6109")
    assert rate == Decimal("30")


@pytest.mark.unit
def test_get_tec_rate_prefix_match(temp_config_dir):
    """Test getting TEC rate with prefix matching."""
    config = TariffConfig(temp_config_dir)

    # Should match "6109" prefix
    rate = config.get_tec_rate("610910")
    assert rate == Decimal("30")


@pytest.mark.unit
def test_get_tec_rate_default(temp_config_dir):
    """Test getting default TEC rate for unknown code."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_tec_rate("9999")
    assert rate == Decimal("20")  # Default rate


@pytest.mark.unit
def test_get_vat_rate_by_country(temp_config_dir):
    """Test getting VAT rate for specific country."""
    config = TariffConfig(temp_config_dir)

    rate_cm = config.get_vat_rate("CM")
    assert rate_cm == Decimal("19.25")

    rate_ga = config.get_vat_rate("GA")
    assert rate_ga == Decimal("18.0")


@pytest.mark.unit
def test_get_vat_rate_default(temp_config_dir):
    """Test getting default VAT rate for unknown country."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_vat_rate("XX")
    assert rate == Decimal("19.25")  # CEMAC default


@pytest.mark.unit
def test_get_exemption(temp_config_dir):
    """Test getting exemption details."""
    config = TariffConfig(temp_config_dir)

    exemption = config.get_exemption("EXO_MEDICAL")
    assert exemption is not None
    assert exemption["dd_rate"] == 0
    assert exemption["vat_rate"] == 0


@pytest.mark.unit
def test_get_exemption_not_found(temp_config_dir):
    """Test getting non-existent exemption."""
    config = TariffConfig(temp_config_dir)

    exemption = config.get_exemption("NONEXISTENT")
    assert exemption is None


@pytest.mark.unit
def test_get_exchange_rate_usd(temp_config_dir):
    """Test getting USD exchange rate."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_exchange_rate("USD")
    assert rate == Decimal("600")


@pytest.mark.unit
def test_get_exchange_rate_eur(temp_config_dir):
    """Test getting EUR exchange rate."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_exchange_rate("EUR")
    assert rate == Decimal("655.957")


@pytest.mark.unit
def test_get_exchange_rate_fcfa(temp_config_dir):
    """Test getting FCFA exchange rate (should be 1)."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_exchange_rate("XAF")
    assert rate == Decimal("1")


@pytest.mark.unit
def test_get_exchange_rate_default(temp_config_dir):
    """Test getting default exchange rate for unknown currency."""
    config = TariffConfig(temp_config_dir)

    rate = config.get_exchange_rate("XXX")
    assert rate == Decimal("600")  # Default


@pytest.mark.unit
def test_get_documents_for_hs(temp_config_dir):
    """Test getting required documents for HS code."""
    # Create HS documents mapping
    docs_data = {
        "_defaults": ["Facture commerciale originale", "Liste de colisage"],
        "6109": ["Certificat d'origine"],
        "8517": ["Certificat de conformité", "Facture commerciale originale"],
    }

    docs_path = temp_config_dir.parent / "documents"
    docs_path.mkdir(exist_ok=True)
    (docs_path / "hs_documents.yaml").write_text(yaml.dump(docs_data), encoding="utf-8")

    config = TariffConfig(temp_config_dir)

    docs = config.get_documents_for_hs("6109")
    assert "Facture commerciale originale" in docs
    assert "Liste de colisage" in docs
    assert "Certificat d'origine" in docs


@pytest.mark.unit
def test_get_documents_for_hs_prefix_match(temp_config_dir):
    """Test document lookup with prefix matching."""
    docs_data = {
        "_defaults": ["Facture commerciale originale"],
        "61": ["Certificat textile"],
        "6109": ["Certificat coton"],
    }

    docs_path = temp_config_dir.parent / "documents"
    docs_path.mkdir(exist_ok=True)
    (docs_path / "hs_documents.yaml").write_text(yaml.dump(docs_data), encoding="utf-8")

    config = TariffConfig(temp_config_dir)

    # Should match longest prefix "6109"
    docs = config.get_documents_for_hs("610910")
    assert "Certificat coton" in docs
    assert "Facture commerciale originale" in docs


@pytest.mark.unit
def test_get_documents_for_hs_default_only(temp_config_dir):
    """Test document lookup with only defaults."""
    docs_data = {
        "_defaults": ["Facture commerciale originale", "Liste de colisage"],
    }

    docs_path = temp_config_dir.parent / "documents"
    docs_path.mkdir(exist_ok=True)
    (docs_path / "hs_documents.yaml").write_text(yaml.dump(docs_data), encoding="utf-8")

    config = TariffConfig(temp_config_dir)

    docs = config.get_documents_for_hs("9999")
    assert len(docs) == 2
    assert "Facture commerciale originale" in docs
    assert "Liste de colisage" in docs


@pytest.mark.unit
def test_config_lazy_loading(temp_config_dir):
    """Test that config files are loaded lazily."""
    config = TariffConfig(temp_config_dir)

    # Access should trigger loading
    assert config._tec_rates is None  # Not loaded yet
    _ = config.tec_rates  # Trigger load
    assert config._tec_rates is not None  # Now loaded


@pytest.mark.unit
def test_config_missing_files(temp_config_dir):
    """Test behavior when config files are missing."""
    # Remove a config file
    (temp_config_dir / "cemac_tec.yaml").unlink()

    config = TariffConfig(temp_config_dir)

    # Should return empty dict or default
    tec_rates = config.tec_rates
    assert isinstance(tec_rates, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])

