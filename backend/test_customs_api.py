# -*- coding: utf-8 -*-
"""
Script de test pour l'API de calcul douanier.

Teste plusieurs cas d'usage via POST /api/customs/calculate
et génère des exemples de journaux d'audit.
"""

import json
import sys
from pathlib import Path

import requests

# Configuration Windows console pour UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://127.0.0.1:8000/api/customs/calculate"


def test_case(name: str, payload: dict):
    """Teste un cas et affiche les résultats."""
    print(f"\n{'='*80}")
    print(f"📋 Test: {name}")
    print(f"{'='*80}")

    try:
        response = requests.post(API_URL, json=payload, timeout=10)

        if response.status_code != 200:
            print(f"❌ Erreur HTTP {response.status_code}")
            print(f"Détails: {response.text}")
            return None

        result = response.json()

        # Afficher le résumé
        print(f"\n✅ Calcul réussi!")
        print(f"ID: {result['calculation_id']}")
        print(f"\nFacture:")
        print(f"  - N°: {result['input']['invoice_number']}")
        print(f"  - HS: {result['input']['hs_code']}")
        print(f"  - Description: {result['input']['description']}")
        print(f"  - Quantité: {result['input']['quantity']}")
        print(f"  - Prix unitaire: {result['input']['unit_price']} {result['input']['currency']}")
        print(f"  - Incoterm: {result['input']['incoterm']}")
        print(f"  - Origine: {result['input']['origin_country']}")

        print(f"\nConversion Incoterms:")
        conv = result["incoterms_conversion"]
        print(f"  - Valeur originale: {conv['original_value']} FCFA ({conv['original_incoterm']})")
        print(f"  - Fret: {conv['freight_cost']} FCFA")
        print(f"  - Assurance: {conv['insurance_cost']} FCFA")
        print(f"  - Valeur CIF: {conv['cif_value']} FCFA")
        print(f"  - Formule: {conv['formula']}")

        print(f"\nCalculs fiscaux:")
        tax = result["tax_breakdown"]
        print(f"  - Valeur en douane: {result['taxable_base']} FCFA")
        print(
            f"  - Droits de douane ({tax['customs_duty_rate']}%): {tax['customs_duty_amount']} FCFA"
        )

        # Autres taxes
        other_total = sum(float(v) for v in tax["other_taxes"].values())
        print(f"  - Autres taxes: {other_total:,.0f} FCFA")
        for tax_name, amount in tax["other_taxes"].items():
            print(f"    • {tax_name}: {amount} FCFA")

        print(f"  - Base TVA: {tax['vat_base']} FCFA")
        print(f"  - TVA ({tax['vat_rate']}%): {tax['vat_amount']} FCFA")
        print(f"\n💰 TOTAL TAXES: {tax['total_taxes']} FCFA")
        print(f"💰 TOTAL À PAYER: {tax['total_amount']} FCFA")

        # Documents requis
        print(f"\n📄 Documents requis ({len(result['required_documents'])}):")
        for doc in result["required_documents"]:
            print(f"  • {doc}")

        # Avertissements
        if result.get("warnings"):
            print(f"\n⚠️  Avertissements:")
            for warning in result["warnings"]:
                print(f"  • {warning}")

        # Journal d'audit
        audit = result["audit_log"]
        print(f"\n📝 Journal d'audit ({len(audit['entries'])} étapes):")
        for i, entry in enumerate(audit["entries"], 1):
            print(f"  {i}. {entry['step']}")
            print(f"     Formule: {entry['formula']}")
            if entry.get("notes"):
                print(f"     Notes: {entry['notes']}")

        return result

    except requests.exceptions.ConnectionError:
        print(f"❌ Impossible de se connecter à l'API ({API_URL})")
        print("   Assurez-vous que le backend FastAPI est démarré.")
        return None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None


def save_audit_example(result: dict, filename: str):
    """Sauvegarde un exemple de journal d'audit."""
    if result is None:
        return

    # Créer le dossier docs/examples s'il n'existe pas
    examples_dir = Path("docs/examples")
    examples_dir.mkdir(parents=True, exist_ok=True)

    # Sauvegarder le résultat complet
    filepath = examples_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Exemple sauvegardé: {filepath}")


def main():
    """Exécute tous les tests."""
    print("🧪 Tests de l'API de calcul douanier DECLADO-IA")
    print(f"URL: {API_URL}\n")

    # Test 1: Riz de Thaïlande (FOB → CIF)
    result1 = test_case(
        "Riz importé de Thaïlande (FOB)",
        {
            "invoice_number": "INV-2024-001",
            "hs_code": "1006",
            "description": "Riz blanchi, qualité A",
            "quantity": "1",
            "unit_price": "500",
            "currency": "USD",
            "incoterm": "FOB",
            "origin_country": "TH",
            "destination_country": "CM",
        },
    )
    if result1:
        save_audit_example(result1, "audit_riz_thailande.json")

    # Test 2: T-shirts de Chine (CIF)
    result2 = test_case(
        "T-shirts en coton de Chine (CIF)",
        {
            "invoice_number": "INV-2024-002",
            "hs_code": "6109",
            "description": "T-shirts en coton, taille M",
            "quantity": "500",
            "unit_price": "5",
            "currency": "EUR",
            "incoterm": "CIF",
            "origin_country": "CN",
            "destination_country": "CM",
        },
    )
    if result2:
        save_audit_example(result2, "audit_tshirts_chine.json")

    # Test 3: Bijoux de France avec préférence tarifaire
    result3 = test_case(
        "Bijoux en or de France (APE UE-CEMAC)",
        {
            "invoice_number": "INV-2024-003",
            "hs_code": "7113",
            "description": "Collier en or 18 carats",
            "quantity": "1",
            "unit_price": "3000",
            "currency": "EUR",
            "incoterm": "FOB",
            "origin_country": "FR",
            "destination_country": "CM",
        },
    )
    if result3:
        save_audit_example(result3, "audit_bijoux_france.json")

    # Test 4: Médicaments avec exonération
    result4 = test_case(
        "Médicaments essentiels (exonération)",
        {
            "invoice_number": "INV-2024-004",
            "hs_code": "3004",
            "description": "Paracétamol 500mg",
            "quantity": "100",
            "unit_price": "50",
            "currency": "USD",
            "incoterm": "CIF",
            "origin_country": "IN",
            "destination_country": "CM",
            "exemption_code": "EXO_MEDICAL",
        },
    )
    if result4:
        save_audit_example(result4, "audit_medicaments_exoneration.json")

    # Test 5: Produits CEMAC (libre circulation)
    result5 = test_case(
        "Produits d'origine CEMAC (Gabon)",
        {
            "invoice_number": "INV-2024-005",
            "hs_code": "8517",
            "description": "Équipements télécoms fabriqués au Gabon",
            "quantity": "10",
            "unit_price": "200000",
            "currency": "XAF",
            "incoterm": "FOB",
            "origin_country": "GA",
            "destination_country": "CM",
            "freight_cost": "50000",
            "insurance_cost": "10000",
        },
    )
    if result5:
        save_audit_example(result5, "audit_telecoms_gabon.json")

    print(f"\n{'='*80}")
    print("✅ Tests terminés!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
