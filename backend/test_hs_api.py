#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de test pour l'API de classification HS
"""
import json
import sys

import requests

# Force UTF-8 encoding for output
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


def main():
    print("=" * 60)
    print("TEST DU SYSTEME DE CLASSIFICATION HS - V1 BASELINE")
    print("=" * 60)

    # Configuration
    API_URL = "http://127.0.0.1:8000/api/hs/suggest"

    # Liste de produits de test
    test_cases = [
        {
            "description": "cotton t-shirt white large",
            "expected_code": "6109",
            "category": "Vetements en coton",
        },
        {
            "description": "smartphone android 5G 256GB",
            "expected_code": "8517",
            "category": "Telephones mobiles",
        },
        {
            "description": "basmati rice 25kg premium quality",
            "expected_code": "1006",
            "category": "Riz",
        },
        {
            "description": "frozen shrimp peeled cooked",
            "expected_code": "0306",
            "category": "Fruits de mer congeles",
        },
        {"description": "milk chocolate bar 100g", "expected_code": "1806", "category": "Chocolat"},
        {
            "description": "electric cordless drill with battery",
            "expected_code": "8467",
            "category": "Outils electriques",
        },
        {
            "description": "gold necklace with diamonds",
            "expected_code": "7113",
            "category": "Bijoux",
        },
        {"description": "white refined sugar 50kg", "expected_code": "1701", "category": "Sucre"},
    ]

    # Executer les tests
    results = []
    correct_top1 = 0
    correct_top3 = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'-' * 60}")
        print(f"Test {i}/{len(test_cases)}: {test['category']}")
        print(f"Description: \"{test['description']}\"")
        print(f"Code HS attendu: {test['expected_code']}")

        try:
            # Appel API
            response = requests.post(API_URL, json={"text": test["description"], "k": 3}, timeout=5)

            if response.status_code == 200:
                data = response.json()
                suggestions = data["suggestions"]

                # Afficher les predictions
                print(f"\nPredictions (Top-3):")
                top3_codes = []
                for j, sug in enumerate(suggestions, 1):
                    top3_codes.append(sug["code"])
                    keywords_str = ", ".join(sug["keywords"][:3]) if sug["keywords"] else "aucun"
                    check = "[OK]" if sug["code"] == test["expected_code"] else "    "
                    print(f"  {check} {j}. Code {sug['code']} - Score: {sug['score']:.4f}")
                    print(f"       Mots-cles: {keywords_str}")

                # Verifier si le code est dans le top-1 et top-3
                is_top1 = suggestions[0]["code"] == test["expected_code"]
                is_top3 = test["expected_code"] in top3_codes

                if is_top1:
                    correct_top1 += 1
                    print(f"\n[SUCCES] Top-1: Code {test['expected_code']} correctement predit")
                elif is_top3:
                    correct_top3 += 1
                    rank = top3_codes.index(test["expected_code"]) + 1
                    print(f"\n[PARTIEL] Code {test['expected_code']} trouve en position {rank}")
                else:
                    print(f"\n[ECHEC] Code {test['expected_code']} absent du top-3")

                results.append(
                    {
                        "test": test["category"],
                        "top1": is_top1,
                        "top3": is_top3,
                        "predicted": suggestions[0]["code"],
                        "score": suggestions[0]["score"],
                    }
                )

            else:
                print(f"[ERREUR] API: {response.status_code}")
                print(response.text)
                results.append(
                    {
                        "test": test["category"],
                        "top1": False,
                        "top3": False,
                        "error": response.status_code,
                    }
                )

        except Exception as e:
            print(f"[EXCEPTION] {e}")
            results.append(
                {"test": test["category"], "top1": False, "top3": False, "error": str(e)}
            )

    # Resume des resultats
    print(f"\n{'=' * 60}")
    print("RESUME DES RESULTATS")
    print("=" * 60)

    total = len(test_cases)
    top1_accuracy = (correct_top1 / total) * 100
    top3_accuracy = ((correct_top1 + correct_top3) / total) * 100

    print(f"\nMetriques de performance:")
    print(f"  - Tests executes: {total}")
    print(f"  - Top-1 corrects: {correct_top1}/{total} ({top1_accuracy:.1f}%)")
    print(f"  - Top-3 corrects: {correct_top1 + correct_top3}/{total} ({top3_accuracy:.1f}%)")

    print(f"\nCritere d'acceptation:")
    if top3_accuracy >= 80:
        print(f"  [VALIDE] Top-3 accuracy >= 80% ({top3_accuracy:.1f}%)")
    elif top3_accuracy >= 60:
        print(f"  [ACCEPTABLE] Top-3 accuracy entre 60-80% ({top3_accuracy:.1f}%)")
    else:
        print(f"  [NON VALIDE] Top-3 accuracy < 60% ({top3_accuracy:.1f}%)")

    print(f"\nNote: Ce test utilise un dataset synthetique de 40 echantillons.")
    print(f"Pour une evaluation rigoureuse, utiliser un dataset reel avec split train/test.")
    print("=" * 60)

    return top3_accuracy >= 60  # Return success if >= 60%


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
