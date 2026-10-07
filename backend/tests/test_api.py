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
    """Suggestion HS : contrat utilisé par l'interface ({text, k} → suggestions)."""
    response = client.post("/api/hs/suggest", json={"text": "ordinateur portable Dell", "k": 3})
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert 0 < len(suggestions) <= 3
    for s in suggestions:
        assert isinstance(s["code"], str) and s["code"]
        assert isinstance(s["score"], float)
        assert isinstance(s["keywords"], list)


def test_hs_suggest_respects_k():
    """Le nombre de suggestions suit k."""
    response = client.post("/api/hs/suggest", json={"text": "smartphone Samsung Galaxy", "k": 1})
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1


def test_hs_suggest_validation():
    """Texte vide refusé ; champ obligatoire absent refusé."""
    assert client.post("/api/hs/suggest", json={"text": ""}).status_code == 400
    assert client.post("/api/hs/suggest", json={"product_description": "ab"}).status_code == 422
