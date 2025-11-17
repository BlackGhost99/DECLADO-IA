"""
Test direct du calculateur douanier (sans API).

Teste le moteur de règles directement et génère des exemples de journaux d'audit.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

# Ajouter le répertoire parent au path pour importer app
sys.path.insert(0, str(Path(__file__).parent))

from app.rules_engine import CalculationInput, CustomsCalculator


def test_case(name: str, calc_input: CalculationInput):
    """Teste un cas et affiche les résultats."""
    print(f"\n{'='*80}")
    print(f"📋 Test: {name}")
    print(f"{'='*80}")

    try:
        calculator = CustomsCalculator()
        result = calculator.calculate(calc_input)

        # Afficher le résumé
        print("\n✅ Calcul réussi!")
        print(f"ID: {result.calculation_id}")
        print(f"\nFacture:")
        print(f"  - N°: {result.input_data.invoice_number}")
        print(f"  - HS: {result.input_data.hs_code}")
        print(f"  - Description: {result.input_data.description}")
        print(f"  - Quantité: {result.input_data.quantity}")
        print(f"  - Prix unitaire: {result.input_data.unit_price} {result.input_data.currency}")
        print(f"  - Incoterm: {result.input_data.incoterm}")
        print(f"  - Origine: {result.input_data.origin_country}")

        print(f"\nConversion Incoterms:")
        conv = result.incoterms_conversion
        print(f"  - Valeur originale: {conv.original_value:,.0f} FCFA ({conv.original_incoterm})")
        print(f"  - Fret: {conv.freight_cost:,.0f} FCFA")
        print(f"  - Assurance: {conv.insurance_cost:,.0f} FCFA")
        print(f"  - Valeur CIF: {conv.cif_value:,.0f} FCFA")
        print(f"  - Formule: {conv.formula_applied}")

        print(f"\nCalculs fiscaux:")
        tax = result.tax_breakdown
        print(f"  - Valeur en douane: {result.taxable_base:,.0f} FCFA")
        print(
            f"  - Droits de douane ({tax.customs_duty_rate}%): {tax.customs_duty_amount:,.0f} FCFA"
        )

        # Autres taxes
        other_total = sum(tax.other_taxes.values())
        print(f"  - Autres taxes: {other_total:,.0f} FCFA")
        for tax_name, amount in tax.other_taxes.items():
            print(f"    • {tax_name}: {amount:,.0f} FCFA")

        print(f"  - Base TVA: {tax.vat_base:,.0f} FCFA")
        print(f"  - TVA ({tax.vat_rate}%): {tax.vat_amount:,.0f} FCFA")
        print(f"\n💰 TOTAL TAXES: {tax.total_taxes:,.0f} FCFA")
        print(f"💰 TOTAL À PAYER: {tax.total_amount:,.0f} FCFA")

        # Documents requis
        print(f"\n📄 Documents requis ({len(result.required_documents)}):")
        for doc in result.required_documents[:5]:  # Limiter à 5 pour lisibilité
            print(f"  • {doc}")
        if len(result.required_documents) > 5:
            print(f"  ... et {len(result.required_documents) - 5} autres")

        # Avertissements
        if result.warnings:
            print(f"\n⚠️  Avertissements:")
            for warning in result.warnings:
                print(f"  • {warning}")

        # Journal d'audit
        audit = result.audit_log
        print(f"\n📝 Journal d'audit ({len(audit.entries)} étapes):")
        for i, entry in enumerate(audit.entries, 1):
            print(f"  {i}. {entry.step}")
            print(f"     Formule: {entry.formula}")
            if entry.notes:
                print(f"     Notes: {entry.notes}")

        return result

    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback

        traceback.print_exc()
        return None


def save_audit_example(result, filename: str):
    """Sauvegarde un exemple de journal d'audit."""
    if result is None:
        return

    # Créer le dossier docs/examples s'il n'existe pas
    examples_dir = Path(__file__).parent.parent / "docs" / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    # Convertir en dict et sauvegarder
    result_dict = result.to_dict()
    filepath = examples_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Exemple sauvegardé: {filepath}")


def main():
    """Exécute tous les tests."""
    print("🧪 Tests du moteur de calcul douanier DECLADO-IA")
    print("=" * 80 + "\n")

    # Test 1: Riz de Thaïlande (FOB → CIF)
    result1 = test_case(
        "Riz importé de Thaïlande (FOB)",
        CalculationInput(
            invoice_number="INV-2024-001",
            hs_code="1006",
            description="Riz blanchi, qualité A",
            quantity=Decimal("1"),
            unit_price=Decimal("500"),
            currency="USD",
            incoterm="FOB",
            origin_country="TH",
            destination_country="CM",
            exchange_rate=Decimal("600"),
        ),
    )
    if result1:
        save_audit_example(result1, "audit_riz_thailande.json")

    # Test 2: T-shirts de Chine (CIF)
    result2 = test_case(
        "T-shirts en coton de Chine (CIF)",
        CalculationInput(
            invoice_number="INV-2024-002",
            hs_code="6109",
            description="T-shirts en coton, taille M",
            quantity=Decimal("500"),
            unit_price=Decimal("5"),
            currency="EUR",
            incoterm="CIF",
            origin_country="CN",
            destination_country="CM",
            exchange_rate=Decimal("655.957"),
        ),
    )
    if result2:
        save_audit_example(result2, "audit_tshirts_chine.json")

    # Test 3: Bijoux de France avec préférence tarifaire
    result3 = test_case(
        "Bijoux en or de France (APE UE-CEMAC)",
        CalculationInput(
            invoice_number="INV-2024-003",
            hs_code="7113",
            description="Collier en or 18 carats",
            quantity=Decimal("1"),
            unit_price=Decimal("3000"),
            currency="EUR",
            incoterm="FOB",
            origin_country="FR",
            destination_country="CM",
            exchange_rate=Decimal("655.957"),
        ),
    )
    if result3:
        save_audit_example(result3, "audit_bijoux_france.json")

    # Test 4: Médicaments avec exonération
    result4 = test_case(
        "Médicaments essentiels (exonération)",
        CalculationInput(
            invoice_number="INV-2024-004",
            hs_code="3004",
            description="Paracétamol 500mg",
            quantity=Decimal("100"),
            unit_price=Decimal("50"),
            currency="USD",
            incoterm="CIF",
            origin_country="IN",
            destination_country="CM",
            exchange_rate=Decimal("600"),
            exemption_code="EXO_MEDICAL",
        ),
    )
    if result4:
        save_audit_example(result4, "audit_medicaments_exoneration.json")

    # Test 5: Produits CEMAC (libre circulation)
    result5 = test_case(
        "Produits d'origine CEMAC (Gabon)",
        CalculationInput(
            invoice_number="INV-2024-005",
            hs_code="8517",
            description="Équipements télécoms fabriqués au Gabon",
            quantity=Decimal("10"),
            unit_price=Decimal("200000"),
            currency="XAF",
            incoterm="FOB",
            origin_country="GA",
            destination_country="CM",
            freight_cost=Decimal("50000"),
            insurance_cost=Decimal("10000"),
            exchange_rate=Decimal("1"),
        ),
    )
    if result5:
        save_audit_example(result5, "audit_telecoms_gabon.json")

    print(f"\n{'='*80}")
    print("✅ Tests terminés!")
    print("📁 Exemples de journaux d'audit générés dans docs/examples/")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
