"""
Test complet: démarre serveur → teste classification → arrête serveur
"""

import subprocess
import sys
import time
from pathlib import Path

import requests

backend_dir = Path(__file__).parent.parent
venv_python = backend_dir.parent / ".venv" / "Scripts" / "python.exe"

print("🚀 Démarrage du serveur backend...")

# Lancer uvicorn en arrière-plan
server_process = subprocess.Popen(
    [str(venv_python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=str(backend_dir),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Attendre que le serveur démarre
print("⏳ Attente du démarrage (5 secondes)...")
time.sleep(5)

# Vérifier que le serveur répond
try:
    response = requests.get("http://127.0.0.1:8000/api/health/ping", timeout=2)
    if response.status_code == 200:
        print("✅ Serveur démarré!\n")
    else:
        print("❌ Serveur ne répond pas correctement")
        server_process.terminate()
        sys.exit(1)
except Exception as e:
    print(f"❌ Erreur de connexion: {e}")
    server_process.terminate()
    sys.exit(1)

# Test cases
test_cases = [
    ("T-shirt en coton blanc pour homme", "6109"),
    ("Ordinateur portable Dell 15 pouces", "8471"),
    ("Café arabica bio en grains", "0901"),
    ("Smartphone Samsung Galaxy S24", "8517"),
    ("Pantalon jean denim bleu", "6203"),
    ("Vin rouge Bordeaux 2020", "2204"),
]

print("=" * 80)
print("🧪 Tests de classification HS")
print("=" * 80 + "\n")

passed = 0
failed = 0

for description, expected_code in test_cases:
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/hs/suggest", json={"text": description, "k": 3}, timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            suggestions = result.get("suggestions", [])

            if suggestions:
                top_code = suggestions[0].get("code", "N/A")
                top_score = suggestions[0].get("score", 0.0)

                # Vérifier si le code attendu est dans le top 3
                all_codes = [s.get("code") for s in suggestions]
                match = expected_code in all_codes

                status = "✅" if match else "⚠️"
                print(f"{status} '{description}'")
                print(f"   Attendu: HS {expected_code}")
                print(f"   Obtenu:  HS {top_code} ({top_score:.1%} confidence)")

                if match:
                    passed += 1
                else:
                    failed += 1
                    print(f"   Top-3: {', '.join(['HS ' + c for c in all_codes])}")
            else:
                print(f"❌ '{description}' - Aucune suggestion retournée")
                failed += 1
        else:
            print(f"❌ '{description}' - Erreur HTTP {response.status_code}")
            failed += 1

        print()

    except Exception as e:
        print(f"❌ Exception pour '{description}': {e}\n")
        failed += 1

# Résultats
print("=" * 80)
print(f"📊 Résultats: {passed}/{len(test_cases)} tests réussis")
if failed > 0:
    print(f"   ⚠️  {failed} échecs détectés")
print("=" * 80)

# Arrêter le serveur
print("\n🛑 Arrêt du serveur...")
server_process.terminate()
server_process.wait(timeout=5)
print("✅ Serveur arrêté")

sys.exit(0 if failed == 0 else 1)
