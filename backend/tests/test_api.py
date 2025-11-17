"""
Tests pour les endpoints API
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    """Test du endpoint racine"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert data["version"] == "0.1.0"


def test_health_ping():
    """Test du health ping (sans DB)"""
    response = client.get("/api/health/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pong"
    assert "timestamp" in data


def test_health_check():
    """Test du health check complet (avec DB)"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "database" in data
    assert data["version"] == "0.1.0"


def test_ocr_demo():
    """Test de l'endpoint OCR demo"""
    payload = {"text": "Facture N°12345 montant 1500.50 EUR"}
    response = client.post("/api/ocr/demo", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "word_count" in data
    assert "char_count" in data
    assert "detected_numbers" in data
    assert data["word_count"] == 5
    assert "12345" in data["detected_numbers"]
    assert "1500.50" in data["detected_numbers"]


def test_ocr_demo_validation():
    """Test de la validation OCR"""
    # Texte vide
    response = client.post("/api/ocr/demo", json={"text": ""})
    assert response.status_code == 422  # Validation error


def test_hs_suggest():
    """Test de la suggestion HS"""
    payload = {"product_description": "ordinateur portable Dell"}
    response = client.post("/api/hs/suggest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "suggested_codes" in data
    assert len(data["suggested_codes"]) > 0
    # Vérifier que le code ordinateur est suggéré
    codes = [c["code"] for c in data["suggested_codes"]]
    assert any("8471" in code for code in codes)


def test_hs_suggest_phone():
    """Test suggestion HS pour téléphone"""
    payload = {"product_description": "smartphone Samsung Galaxy"}
    response = client.post("/api/hs/suggest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["suggested_codes"]) > 0
    # Vérifier que le code téléphone est suggéré
    codes = [c["code"] for c in data["suggested_codes"]]
    assert any("8517" in code for code in codes)


def test_hs_suggest_unknown():
    """Test suggestion HS pour produit inconnu"""
    payload = {"product_description": "produit mystérieux XYZ"}
    response = client.post("/api/hs/suggest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["suggested_codes"]) > 0
    # Code par défaut
    assert data["suggested_codes"][0]["code"] == "9999.00"


def test_hs_suggest_validation():
    """Test de la validation HS"""
    # Description trop courte
    response = client.post("/api/hs/suggest", json={"product_description": "ab"})
    assert response.status_code == 422  # Validation error
