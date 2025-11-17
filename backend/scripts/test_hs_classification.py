"""
Script pour tester la classification HS du nouveau modèle.
"""

import json

import requests

API_URL = "http://127.0.0.1:8000/api/hs/suggest"

# Test cases avec vraies descriptions de produits
test_cases = [
    "T-shirt en coton blanc pour homme",
    "Ordinateur portable Dell 15 pouces",
    "Café arabica bio en grains",
    "Smartphone Samsung Galaxy S24",
    "Pantalon jean denim bleu",
    "Vin rouge Bordeaux 2020",
    "Table en bois massif chêne",
    "Téléviseur LED 55 pouces 4K",
    "Fromage camembert lait cru",
    "Voiture Peugeot 208 essence",
]

print("🧪 Test de classification HS avec le nouveau modèle\n")
print("=" * 80)

for description in test_cases:
    try:
        response = requests.post(API_URL, json={"text": description, "k": 3}, timeout=5)

        if response.status_code == 200:
            result = response.json()
            print(f"\n📦 '{description}'")
            print(f"   Suggestions:")

            for suggestion in result.get("suggestions", []):
                code = suggestion.get("code", "N/A")
                score = suggestion.get("score", 0.0)
                keywords = ", ".join(suggestion.get("keywords", [])[:3])
                print(f"      • HS {code} - {score:.1%} confidence")
                if keywords:
                    print(f"        Mots-clés: {keywords}")
        else:
            print(f"\n❌ Erreur {response.status_code} pour: {description}")

    except Exception as e:
        print(f"\n❌ Exception pour '{description}': {e}")

print("\n" + "=" * 80)
print("✅ Test terminé!")
