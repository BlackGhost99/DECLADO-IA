"""
Unit Tests - Incoterms Conversions
Phase 10: Tests, QA et Performance
"""

from decimal import Decimal

import pytest

from app.rules_engine.incoterms import (
    calculate_freight_default,
    calculate_insurance_default,
    cfr_to_cif,
    convert_to_cif,
    fob_to_cfr,
    fob_to_cif,
    round_fcfa,
)


# ============================================================================
# Rounding Tests
# ============================================================================


@pytest.mark.unit
def test_round_fcfa_half_up():
    """Test FCFA rounding (0.5 rounds up)."""
    assert round_fcfa(Decimal("100.4")) == Decimal("100")
    assert round_fcfa(Decimal("100.5")) == Decimal("101")  # Rounds up
    assert round_fcfa(Decimal("100.6")) == Decimal("101")
    assert round_fcfa(Decimal("99.49")) == Decimal("99")
    assert round_fcfa(Decimal("99.50")) == Decimal("100")  # Rounds up


@pytest.mark.unit
def test_round_fcfa_negative():
    """Test rounding of negative amounts."""
    assert round_fcfa(Decimal("-100.5")) == Decimal("-101")
    assert round_fcfa(Decimal("-100.4")) == Decimal("-100")


# ============================================================================
# Freight Calculation Tests
# ============================================================================


@pytest.mark.unit
def test_calculate_freight_default():
    """Test default freight calculation (10% of FOB)."""
    fob_value = Decimal("100000")
    freight = calculate_freight_default(fob_value, "CN", "CM")

    assert freight == Decimal("10000"), f"Expected 10000, got {freight}"


@pytest.mark.unit
def test_calculate_freight_default_zero():
    """Test freight calculation with zero FOB."""
    freight = calculate_freight_default(Decimal("0"), "CN", "CM")
    assert freight == Decimal("0")


# ============================================================================
# Insurance Calculation Tests
# ============================================================================


@pytest.mark.unit
def test_calculate_insurance_default_0_5_percent():
    """Test insurance calculation at 0.5% rate."""
    cfr_value = Decimal("100000")
    insurance = calculate_insurance_default(cfr_value)

    # 0.5% of 100000 = 500, but minimum is 5000
    assert insurance == Decimal("5000"), f"Expected minimum 5000, got {insurance}"


@pytest.mark.unit
def test_calculate_insurance_default_above_minimum():
    """Test insurance calculation above minimum threshold."""
    cfr_value = Decimal("2000000")  # 2M FCFA
    insurance = calculate_insurance_default(cfr_value)

    # 0.5% of 2000000 = 10000 (above minimum)
    assert insurance == Decimal("10000"), f"Expected 10000, got {insurance}"


# ============================================================================
# FOB to CFR Conversion Tests
# ============================================================================


@pytest.mark.unit
def test_fob_to_cfr_with_freight():
    """Test FOB to CFR conversion with provided freight."""
    fob_value = Decimal("100000")
    freight_cost = Decimal("15000")

    cfr_value, used_freight = fob_to_cfr(fob_value, freight_cost, "CN", "CM")

    assert cfr_value == Decimal("115000")
    assert used_freight == freight_cost


@pytest.mark.unit
def test_fob_to_cfr_without_freight():
    """Test FOB to CFR conversion with default freight."""
    fob_value = Decimal("100000")

    cfr_value, used_freight = fob_to_cfr(fob_value, None, "CN", "CM")

    # Default freight is 10% of FOB = 10000
    assert cfr_value == Decimal("110000")
    assert used_freight == Decimal("10000")


# ============================================================================
# CFR to CIF Conversion Tests
# ============================================================================


@pytest.mark.unit
def test_cfr_to_cif_with_insurance():
    """Test CFR to CIF conversion with provided insurance."""
    cfr_value = Decimal("110000")
    insurance_cost = Decimal("6000")

    cif_value, used_insurance = cfr_to_cif(cfr_value, insurance_cost)

    assert cif_value == Decimal("116000")
    assert used_insurance == insurance_cost


@pytest.mark.unit
def test_cfr_to_cif_without_insurance():
    """Test CFR to CIF conversion with default insurance."""
    cfr_value = Decimal("110000")

    cif_value, used_insurance = cfr_to_cif(cfr_value, None)

    # Default insurance is max(0.5% of CFR, 5000) = max(550, 5000) = 5000
    assert cif_value == Decimal("115000")
    assert used_insurance == Decimal("5000")


# ============================================================================
# FOB to CIF Conversion Tests
# ============================================================================


@pytest.mark.unit
def test_fob_to_cif_complete():
    """Test complete FOB to CIF conversion."""
    fob_value = Decimal("100000")
    freight_cost = Decimal("10000")
    insurance_cost = Decimal("5000")

    cif_value, freight, insurance = fob_to_cif(
        fob_value, freight_cost, insurance_cost, "CN", "CM"
    )

    assert cif_value == Decimal("115000")
    assert freight == freight_cost
    assert insurance == insurance_cost


@pytest.mark.unit
def test_fob_to_cif_defaults():
    """Test FOB to CIF with default freight and insurance."""
    fob_value = Decimal("100000")

    cif_value, freight, insurance = fob_to_cif(fob_value, None, None, "CN", "CM")

    # FOB 100000 + Freight 10000 (10%) + Insurance 5000 (min) = 115000
    assert cif_value == Decimal("115000")
    assert freight == Decimal("10000")
    assert insurance == Decimal("5000")


# ============================================================================
# Generic Incoterm Conversion Tests
# ============================================================================


@pytest.mark.unit
def test_convert_to_cif_from_cif():
    """Test conversion when already CIF."""
    value = Decimal("100000")
    cif_value, freight, insurance, formula = convert_to_cif(
        value, "CIF", None, None, "CN", "CM"
    )

    assert cif_value == value
    assert formula == "CIF (aucune conversion)"


@pytest.mark.unit
def test_convert_to_cif_from_cfr():
    """Test conversion from CFR to CIF."""
    cfr_value = Decimal("110000")
    cif_value, freight, insurance, formula = convert_to_cif(
        cfr_value, "CFR", None, None, "CN", "CM"
    )

    assert cif_value > cfr_value  # Should add insurance
    assert "CFR" in formula


@pytest.mark.unit
def test_convert_to_cif_from_fob():
    """Test conversion from FOB to CIF."""
    fob_value = Decimal("100000")
    cif_value, freight, insurance, formula = convert_to_cif(
        fob_value, "FOB", None, None, "CN", "CM"
    )

    assert cif_value > fob_value  # Should add freight and insurance
    assert "FOB" in formula


@pytest.mark.unit
def test_convert_to_cif_from_exw():
    """Test conversion from EXW (adds pre-shipment costs)."""
    exw_value = Decimal("100000")
    cif_value, freight, insurance, formula = convert_to_cif(
        exw_value, "EXW", None, None, "CN", "CM"
    )

    assert cif_value > exw_value
    assert "EXW" in formula or "5%" in formula


@pytest.mark.unit
def test_convert_to_cif_from_ddp():
    """Test conversion from DDP (treated as CFR-like)."""
    ddp_value = Decimal("120000")
    cif_value, freight, insurance, formula = convert_to_cif(
        ddp_value, "DDP", None, None, "CN", "CM"
    )

    assert cif_value > ddp_value  # Should add insurance
    assert "DDP" in formula or "CFR" in formula


@pytest.mark.unit
def test_convert_to_cif_unknown_incoterm():
    """Test conversion with unknown incoterm (defaults to FOB)."""
    value = Decimal("100000")
    cif_value, freight, insurance, formula = convert_to_cif(
        value, "UNKNOWN", None, None, "CN", "CM"
    )

    assert cif_value > value
    assert "inconnu" in formula.lower() or "FOB" in formula


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_convert_to_cif_zero_value():
    """Test conversion with zero value."""
    cif_value, freight, insurance, formula = convert_to_cif(
        Decimal("0"), "FOB", None, None, "CN", "CM"
    )

    assert cif_value >= Decimal("0")
    assert insurance >= Decimal("5000")  # Minimum insurance


@pytest.mark.unit
def test_convert_to_cif_very_large_value():
    """Test conversion with very large value."""
    large_value = Decimal("1000000000")  # 1 billion FCFA
    cif_value, freight, insurance, formula = convert_to_cif(
        large_value, "FOB", None, None, "CN", "CM"
    )

    assert cif_value > large_value
    # Insurance should be 0.5% of CFR (not minimum)
    assert insurance > Decimal("5000")


@pytest.mark.unit
def test_convert_to_cif_case_insensitive():
    """Test that incoterm matching is case-insensitive."""
    value = Decimal("100000")

    cif1, _, _, _ = convert_to_cif(value, "fob", None, None, "CN", "CM")
    cif2, _, _, _ = convert_to_cif(value, "FOB", None, None, "CN", "CM")
    cif3, _, _, _ = convert_to_cif(value, "Fob", None, None, "CN", "CM")

    assert cif1 == cif2 == cif3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])

