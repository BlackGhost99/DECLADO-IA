"""Test de classification HS avec le serveur backend."""

import subprocess
import sys
import time
from pathlib import Path

import requests

# Descriptions à tester avec les données CEMAC
TEST_CASES = [
    "Lait en poudre pour bébé",
    "Cheveux bruts non traités",
    "Soies de porc naturelles",
    "Poulets vivants de moins de 185 grammes",
    "Chèvres vivantes",
    "Lait concentré non sucré",
    "Crème de lait fraîche",
]


def main():
    # Démarrer le serveur
    backend_dir = Path(__file__).parents[1]
    venv_python = backend_dir.parents[0] / ".venv" / "Scripts" / "python.exe"

    print("🚀 Démarrage du serveur sur http://127.0.0.1:8001...")
    server = subprocess.Popen(
        [
            str(venv_python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ],
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Attendre que le serveur démarre (avec vérification progressive)
    print("⏳ Attente du démarrage du serveur...")
    max_wait = 15
    for i in range(max_wait):
        time.sleep(1)
        try:
            resp = requests.get("http://127.0.0.1:8001/api/health/ping", timeout=2)
            if resp.status_code == 200:
                break
        except Exception:
            pass
        if i == max_wait - 1:
            print("❌ Timeout: le serveur n'a pas démarré")
            server.terminate()
            return 1

    try:
        # Vérifier que le serveur répond
        response = requests.get("http://127.0.0.1:8001/api/health/ping", timeout=5)
        if response.status_code != 200:
            print(f"❌ Serveur ne répond pas: {response.status_code}")
            return 1

        print("✅ Serveur démarré!\n")
        print("=" * 70)
        print("TESTS DE CLASSIFICATION HS AVEC DONNÉES CEMAC")
        print("=" * 70)

        # Tester chaque description
        for desc in TEST_CASES:
            print(f"\n📦 Description: '{desc}'")

            response = requests.post(
                "http://127.0.0.1:8001/api/hs/suggest",
                json={"text": desc, "k": 3},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                suggestions = data.get("suggestions", [])
                print(f"   Top 3 suggestions:")
                for i, sug in enumerate(suggestions, 1):
                    code = sug.get("code", "???")
                    confidence = sug.get("score", 0.0)
                    keywords = ", ".join(sug.get("keywords", [])[:3])
                    print(f"      {i}. Code HS: {code} (score: {confidence:.4f})")
                    if keywords:
                        print(f"         Mots-clés: {keywords}")
            else:
                print(f"   ❌ Erreur: {response.status_code}")
                print(f"      {response.text[:200]}")

        print("\n" + "=" * 70)
        print("✅ Tests terminés!")

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")
        return 1

    finally:
        # Arrêter le serveur
        print("\n🛑 Arrêt du serveur...")
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    return 0


if __name__ == "__main__":
    sys.exit(main())
