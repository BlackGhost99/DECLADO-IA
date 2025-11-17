"""
Tests unitaires du moteur de règles douanières.

Validation contre le "golden set" de cas de test calculés manuellement.
"""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.rules_engine import CalculationInput, CustomsCalculator


def load_golden_set():
    """Charge le jeu de tests golden set depuis le fichier YAML."""
    golden_set_path = Path(__file__).parent.parent.parent / "data" / "tests" / "golden_set.yaml"

    with open(golden_set_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data["test_cases"]


def create_calculation_input(test_input: dict) -> CalculationInput:
    """Convertit un dict de test en CalculationInput."""
    return CalculationInput(
        invoice_number=test_input["invoice_number"],
        hs_code=test_input["hs_code"],
        description=test_input["description"],
        quantity=Decimal(test_input["quantity"]),
        unit_price=Decimal(test_input["unit_price"]),
        currency=test_input["currency"],
        incoterm=test_input["incoterm"],
        origin_country=test_input["origin_country"],
        destination_country=test_input.get("destination_country", "CM"),
        freight_cost=(
            Decimal(test_input["freight_cost"]) if test_input.get("freight_cost") else None
        ),
        insurance_cost=(
            Decimal(test_input["insurance_cost"]) if test_input.get("insurance_cost") else None
        ),
        exchange_rate=(
            Decimal(test_input["exchange_rate"]) if test_input.get("exchange_rate") else None
        ),
        exemption_code=test_input.get("exemption_code"),
    )


def assert_within_tolerance(
    actual: Decimal, expected: int | float, tolerance: int, field_name: str
):
    """Vérifie qu'une valeur est dans la tolérance acceptable."""
    expected_decimal = Decimal(str(expected))
    diff = abs(actual - expected_decimal)

    assert diff <= tolerance, (
        f"{field_name}: écart de {diff} FCFA "
        f"(attendu: {expected_decimal}, obtenu: {actual}, tolérance: ±{tolerance})"
    )


@pytest.mark.parametrize("test_case", load_golden_set(), ids=lambda tc: tc["name"])
def test_golden_set_case(test_case):
    """
    Teste chaque cas du golden set.

    Valide que les calculs reproduisent les résultats attendus
    dans la tolérance acceptable (±1 ou ±2 FCFA selon le cas).
    """
    # Préparer les données d'entrée
    calc_input = create_calculation_input(test_case["input"])

    # Exécuter le calcul
    calculator = CustomsCalculator()
    result = calculator.calculate(calc_input)

    # Récupérer les valeurs attendues et la tolérance
    expected = test_case["expected"]
    tolerance = test_case.get("tolerance", 1)

    # Vérifier la valeur CIF
    assert_within_tolerance(
        result.incoterms_conversion.cif_value, expected["cif_value"], tolerance, "Valeur CIF"
    )

    # Vérifier la valeur en douane (base imposable)
    assert_within_tolerance(
        result.taxable_base,
        expected["taxable_base"],
        tolerance,
        "Valeur en douane (base imposable)",
    )

    # Vérifier le taux DD
    assert result.tax_breakdown.customs_duty_rate == Decimal(
        str(expected["dd_rate"])
    ), f"Taux DD incorrect: attendu {expected['dd_rate']}%, obtenu {result.tax_breakdown.customs_duty_rate}%"

    # Vérifier le montant DD
    assert_within_tolerance(
        result.tax_breakdown.customs_duty_amount,
        expected["dd_amount"],
        tolerance,
        "Montant droits de douane (DD)",
    )

    # Vérifier les autres taxes
    other_taxes_total = sum(result.tax_breakdown.other_taxes.values())
    assert_within_tolerance(
        other_taxes_total, expected["other_taxes_total"], tolerance, "Total autres taxes"
    )

    # Vérifier la base TVA
    assert_within_tolerance(
        result.tax_breakdown.vat_base, expected["vat_base"], tolerance, "Base TVA"
    )

    # Vérifier le taux TVA
    assert result.tax_breakdown.vat_rate == Decimal(
        str(expected["vat_rate"])
    ), f"Taux TVA incorrect: attendu {expected['vat_rate']}%, obtenu {result.tax_breakdown.vat_rate}%"

    # Vérifier le montant TVA
    assert_within_tolerance(
        result.tax_breakdown.vat_amount, expected["vat_amount"], tolerance, "Montant TVA"
    )

    # Vérifier le total des taxes
    assert_within_tolerance(
        result.tax_breakdown.total_taxes, expected["total_taxes"], tolerance, "Total taxes"
    )

    # Vérifier le montant total à payer
    assert_within_tolerance(
        result.tax_breakdown.total_amount,
        expected["total_amount"],
        tolerance,
        "Montant total à payer",
    )

    # Vérifier que l'audit log contient au moins les étapes principales
    assert (
        len(result.audit_log.entries) >= 8
    ), f"Audit log incomplet: {len(result.audit_log.entries)} entrées (attendu au moins 8)"

    # Vérifier la présence des étapes clés dans l'audit log
    step_names = {entry.step for entry in result.audit_log.entries}
    required_steps = {
        "Conversion devise",
        "Conversion Incoterms",
        "Valeur en douane",
        "Droits de douane (DD)",
        "Base TVA",
        "Taxe sur la Valeur Ajoutée (TVA)",
        "Totaux",
    }

    missing_steps = required_steps - step_names
    assert not missing_steps, f"Étapes manquantes dans l'audit log: {missing_steps}"

    # Vérifier que le calcul a un ID unique
    assert result.calculation_id, "Calculation ID manquant"
    assert len(result.calculation_id) > 0, "Calculation ID vide"

    # Vérifier que les documents requis sont présents
    assert len(result.required_documents) > 0, "Aucun document requis retourné"
    assert (
        "Facture commerciale originale" in result.required_documents
    ), "Document 'Facture commerciale originale' manquant"

    print(f"\n✓ Test '{test_case['name']}' réussi")
    print(f"  Calcul ID: {result.calculation_id}")
    print(f"  Valeur CIF: {result.incoterms_conversion.cif_value:,.0f} FCFA")
    print(
        f"  DD ({result.tax_breakdown.customs_duty_rate}%): {result.tax_breakdown.customs_duty_amount:,.0f} FCFA"
    )
    print(f"  TVA ({result.tax_breakdown.vat_rate}%): {result.tax_breakdown.vat_amount:,.0f} FCFA")
    print(f"  Total taxes: {result.tax_breakdown.total_taxes:,.0f} FCFA")
    print(f"  Total à payer: {result.tax_breakdown.total_amount:,.0f} FCFA")
    print(f"  Étapes d'audit: {len(result.audit_log.entries)}")


def test_audit_log_detail():
    """Teste le détail du journal d'audit pour un cas simple."""
    calc_input = CalculationInput(
        invoice_number="TEST-001",
        hs_code="1006",
        description="Riz de test",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        currency="USD",
        incoterm="FOB",
        origin_country="TH",
        destination_country="CM",
        exchange_rate=Decimal("600"),
    )

    calculator = CustomsCalculator()
    result = calculator.calculate(calc_input)

    # Vérifier que chaque entrée d'audit a les champs requis
    for entry in result.audit_log.entries:
        assert entry.step, "Nom d'étape manquant"
        assert entry.formula, "Formule manquante"
        assert entry.inputs, "Inputs manquants"
        assert entry.output is not None, "Output manquant"
        assert entry.timestamp, "Timestamp manquant"

    # Vérifier que le journal est sérialisable en dict
    audit_dict = result.audit_log.to_dict()
    assert "calculation_id" in audit_dict
    assert "entries" in audit_dict
    assert isinstance(audit_dict["entries"], list)
    assert len(audit_dict["entries"]) > 0


def test_exemption_validation():
    """Teste la validation des exonérations."""
    # Cas avec exonération médicale
    calc_input = CalculationInput(
        invoice_number="TEST-MEDICAL",
        hs_code="3004",
        description="Médicaments",
        quantity=Decimal("10"),
        unit_price=Decimal("50"),
        currency="USD",
        incoterm="CIF",
        origin_country="IN",
        destination_country="CM",
        exchange_rate=Decimal("600"),
        exemption_code="EXO_MEDICAL",
    )

    calculator = CustomsCalculator()
    result = calculator.calculate(calc_input)

    # Vérifier exonération DD
    assert result.tax_breakdown.customs_duty_rate == Decimal(
        "0"
    ), "Exonération DD médicaments non appliquée"
    assert result.tax_breakdown.customs_duty_amount == Decimal(
        "0"
    ), "Montant DD devrait être 0 avec exonération"

    # Vérifier exonération TVA
    assert result.tax_breakdown.vat_rate == Decimal(
        "0"
    ), "Exonération TVA médicaments non appliquée"
    assert result.tax_breakdown.vat_amount == Decimal(
        "0"
    ), "Montant TVA devrait être 0 avec exonération"


def test_preferential_tariff_cemac():
    """Teste l'application des préférences tarifaires CEMAC."""
    # Produit d'origine gabonaise (exonération DD intracommunautaire)
    calc_input = CalculationInput(
        invoice_number="TEST-CEMAC",
        hs_code="8517",
        description="Équipements télécoms",
        quantity=Decimal("5"),
        unit_price=Decimal("100000"),
        currency="XAF",
        incoterm="FOB",
        origin_country="GA",  # Gabon (pays CEMAC)
        destination_country="CM",
        exchange_rate=Decimal("1"),
    )

    calculator = CustomsCalculator()
    result = calculator.calculate(calc_input)

    # Vérifier exonération DD pour origine CEMAC
    assert result.tax_breakdown.customs_duty_rate == Decimal(
        "0"
    ), "Préférence CEMAC (exonération DD) non appliquée"
    assert result.tax_breakdown.customs_duty_amount == Decimal(
        "0"
    ), "Montant DD devrait être 0 pour origine CEMAC"

    # Vérifier que la TVA s'applique normalement
    assert result.tax_breakdown.vat_rate > Decimal(
        "0"
    ), "TVA devrait s'appliquer même avec préférence CEMAC"


def test_result_serialization():
    """Teste la sérialisation du résultat en dictionnaire pour l'API."""
    calc_input = CalculationInput(
        invoice_number="TEST-SERIAL",
        hs_code="6109",
        description="T-shirts",
        quantity=Decimal("100"),
        unit_price=Decimal("5"),
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
    )

    calculator = CustomsCalculator()
    result = calculator.calculate(calc_input)

    # Convertir en dict
    result_dict = result.to_dict()

    # Vérifier la structure
    assert "calculation_id" in result_dict
    assert "input" in result_dict
    assert "incoterms_conversion" in result_dict
    assert "taxable_base" in result_dict
    assert "tax_breakdown" in result_dict
    assert "required_documents" in result_dict
    assert "audit_log" in result_dict

    # Vérifier que les Decimal sont convertis en string
    assert isinstance(result_dict["taxable_base"], str)
    assert isinstance(result_dict["tax_breakdown"]["customs_duty_amount"], str)
    assert isinstance(result_dict["tax_breakdown"]["vat_amount"], str)

    # Vérifier que l'audit log est sérialisé
    assert "entries" in result_dict["audit_log"]
    assert len(result_dict["audit_log"]["entries"]) > 0


if __name__ == "__main__":
    # Exécuter les tests avec pytest
    pytest.main([__file__, "-v", "-s"])
