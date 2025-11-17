# DECLADO-IA - Test Suite Documentation

**Phase 10: Tests, QA et Performance**

## 📋 Vue d'ensemble

Cette suite de tests garantit la fiabilité, la précision et la robustesse du système DECLADO-IA. Elle couvre:

- ✅ Tests unitaires (pytest) pour logique métier, règles, calculs
- ✅ Tests d'intégration (end-to-end) : pipeline complet sur batch
- ✅ Tests de performance : profil CPU/mémoire, latence d'inférence, traitement batch (200 lignes)
- ✅ Tests de sécurité : tentative d'accès DB, injection, validation fichiers
- ✅ UAT : scénarios réels avec utilisateurs (opérateur/superviseur)

## 🎯 Objectifs

- **Coverage target**: 80% de couverture de code
- **Performance**: 
  - Calcul simple: < 2 secondes
  - Batch 200 lignes: < 30 minutes
  - Mémoire: < 2GB
  - CPU: < 80%
- **Sécurité**: 100% des tests de sécurité passés
- **UAT**: Sign-off utilisateurs requis

## 🚀 Exécution des Tests

### Tous les tests

```bash
cd backend
python -m pytest
```

### Par catégorie

```bash
# Tests unitaires
pytest -m unit

# Tests d'intégration
pytest -m integration

# Tests end-to-end
pytest -m e2e

# Tests de performance
pytest -m performance

# Tests de sécurité
pytest -m security
```

### Avec coverage

```bash
pytest --cov=app --cov-report=html --cov-report=term-missing
```

Le rapport HTML sera généré dans `htmlcov/index.html`.

### Tests lents (batch processing)

```bash
pytest -m "slow"  # Inclut les tests batch 200 items
```

### Exclure les tests lents

```bash
pytest -m "not slow"
```

## 📊 Structure des Tests

```
backend/tests/
├── __init__.py
├── conftest.py              # Fixtures communes
├── test_rules_engine.py     # Tests moteur de règles (golden set)
├── test_unit_incoterms.py   # Tests conversions Incoterms
├── test_unit_config.py      # Tests configuration tarifaire
├── test_performance.py      # Tests performance (CPU/mémoire/latence)
├── test_integration_e2e.py  # Tests end-to-end pipeline
├── test_security.py         # Tests sécurité (injection, validation)
├── test_api.py              # Tests API endpoints
├── test_ocr_pipeline.py     # Tests OCR
├── test_hs_classifier.py    # Tests classification HS
└── test_exports.py          # Tests export PDF/CSV
```

## 🧪 Types de Tests

### 1. Tests Unitaires (`test_unit_*.py`)

**Objectif**: Tester les composants isolés (logique métier, calculs, règles)

**Exemples**:
- Conversions Incoterms (FOB → CFR → CIF)
- Calculs douaniers (DD, TVA, taxes)
- Configuration tarifaire
- Arrondis FCFA

**Marqueur**: `@pytest.mark.unit`

### 2. Tests d'Intégration (`test_integration_*.py`)

**Objectif**: Tester l'interaction entre modules

**Exemples**:
- OCR → Classification HS → Calcul douanier
- API endpoints avec base de données
- Pipeline complet

**Marqueur**: `@pytest.mark.integration`

### 3. Tests End-to-End (`test_integration_e2e.py`)

**Objectif**: Tester le workflow complet utilisateur

**Exemples**:
- Upload PDF → OCR → Classification → Calcul → Export
- Batch processing 200 items

**Marqueur**: `@pytest.mark.e2e`

### 4. Tests de Performance (`test_performance.py`)

**Objectif**: Mesurer latence, CPU, mémoire, throughput

**Métriques**:
- Latence calcul simple: < 2s
- Latence batch 200: < 30 min
- Mémoire: < 2GB
- CPU: < 80%
- Throughput: > 10 calc/s

**Marqueur**: `@pytest.mark.performance`

**Dépendances**: `psutil` pour monitoring CPU/mémoire

### 5. Tests de Sécurité (`test_security.py`)

**Objectif**: Prévenir vulnérabilités

**Couverture**:
- SQL injection
- File upload validation
- Input sanitization
- XSS attempts
- Database encryption

**Marqueur**: `@pytest.mark.security`

## 📈 Rapports de Tests

### Génération automatique

```bash
# Script de test complet avec rapports
python scripts/run_tests.py

# Génération rapport détaillé
python scripts/generate_test_report.py
```

### Rapports générés

- `htmlcov/index.html` - Coverage HTML interactif
- `coverage.xml` - Coverage XML (CI/CD)
- `test_report.json` - Résultats JSON
- `TEST_REPORT.md` - Rapport Markdown

## ✅ Critères d'Acceptation

### Tests Automatisés

- [ ] **Coverage ≥ 80%** (lignes de code)
- [ ] **100% tests unitaires passent**
- [ ] **100% tests intégration passent**
- [ ] **100% tests sécurité passent**
- [ ] **Performance targets atteints**:
  - Calcul simple < 2s
  - Batch 200 < 30 min
  - Mémoire < 2GB

### UAT (User Acceptance Testing)

- [ ] **Scénario 1**: Traitement facture PDF simple ✅
- [ ] **Scénario 2**: Traitement facture complexe ✅
- [ ] **Scénario 3**: Workflow superviseur ✅
- [ ] **Scénario 4**: Gestion cas d'exception ✅
- [ ] **Scénario 5**: Performance & charge ✅

**Voir**: `backend/docs/UAT_CHECKLIST.md` pour la checklist complète.

### Sign-off Requis

- [ ] Opérateur
- [ ] Superviseur
- [ ] Chef de Projet

## 🔧 Configuration

### pytest.ini

Configuration dans `backend/pytest.ini`:
- Coverage target: 80%
- Markers: unit, integration, e2e, performance, security
- Timeout: 300s
- Async mode: auto

### Fixtures (conftest.py)

- `client`: FastAPI test client
- `test_db_session`: Session DB de test
- `temp_pdf_file`: Fichier PDF temporaire
- `temp_image_file`: Image temporaire
- `temp_csv_file`: CSV batch temporaire
- `performance_monitor`: Monitor CPU/mémoire

## 🐛 Debugging

### Exécuter un test spécifique

```bash
pytest tests/test_rules_engine.py::test_golden_set_case -v
```

### Mode verbose

```bash
pytest -v -s  # -s pour voir les print()
```

### Arrêter au premier échec

```bash
pytest -x
```

### Afficher les print()

```bash
pytest -s
```

## 📝 Ajouter de Nouveaux Tests

### Template test unitaire

```python
import pytest
from app.rules_engine import CustomsCalculator

@pytest.mark.unit
def test_my_feature():
    """Test description."""
    # Arrange
    calculator = CustomsCalculator()
    
    # Act
    result = calculator.calculate(input_data)
    
    # Assert
    assert result.taxable_base > 0
```

### Template test performance

```python
@pytest.mark.performance
def test_my_performance(performance_monitor):
    """Test performance."""
    performance_monitor.start()
    
    # Your code here
    
    stats = performance_monitor.stop()
    assert stats['peak_memory_mb'] < 2000
```

## 🚨 Troubleshooting

### Erreur: psutil not found

```bash
pip install psutil==5.9.8
```

### Erreur: Tesseract not found

Les tests OCR nécessitent Tesseract installé. Utiliser le marqueur:

```bash
pytest -m "not requires_tesseract"
```

### Erreur: Coverage < 80%

1. Vérifier `htmlcov/index.html` pour identifier les zones non couvertes
2. Ajouter des tests pour les fonctions non couvertes
3. Exclure les fichiers non testables (voir `pytest.ini`)

## 📚 Ressources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [UAT Checklist](../docs/UAT_CHECKLIST.md)
- [Rules Engine Documentation](../../docs/RULES_ENGINE.md)

## ✅ Checklist Pré-Production

Avant de déployer en production, vérifier:

- [ ] Tous les tests passent (`pytest`)
- [ ] Coverage ≥ 80% (`pytest --cov=app`)
- [ ] Tests performance passent (`pytest -m performance`)
- [ ] Tests sécurité passent (`pytest -m security`)
- [ ] UAT sign-off obtenu (`UAT_CHECKLIST.md`)
- [ ] Rapport de test généré (`TEST_REPORT.md`)
- [ ] Documentation à jour

---

**Phase 10 - Tests, QA et Performance** ✅

