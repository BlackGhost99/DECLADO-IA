# 🧪 DECLADO-IA - Guide de Test du Prototype v0.1

## Vue d'ensemble

Ce prototype démontre l'architecture end-to-end complète de DECLADO-IA :
- ✅ Backend FastAPI avec endpoints fonctionnels
- ✅ Base de données SQLite chiffrée avec SQLCipher
- ✅ Frontend Electron + React
- ✅ Communication bidirectionnelle Electron ↔ Backend
- ✅ Tests automatisés

---

## 🚀 Installation

### Option 1 : Installation Automatique (Recommandé)

```powershell
# Exécuter le script d'installation
.\scripts\setup.ps1
```

Ce script va :
1. Vérifier Python 3.11 et Node.js (les installer si nécessaire)
2. Créer l'environnement virtuel Python
3. Installer toutes les dépendances (Python + Node)
4. Initialiser la base de données chiffrée
5. Créer les dossiers nécessaires

### Option 2 : Installation Manuelle

```powershell
# 1. Backend Python
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Frontend Node
cd ..\frontend
npm install

# 3. Retour à la racine
cd ..
```

---

## 🏃 Lancement de l'Application

### Option A : Script Automatique

```powershell
.\scripts\start-dev.ps1
```

### Option B : Lancement Manuel (2 terminaux)

**Terminal 1 - Backend :**
```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

**Terminal 2 - Frontend :**
```powershell
cd frontend
npm run electron:dev
```

---

## ✅ Critères d'Acceptation - Tests à Effectuer

### 1. **Backend API Fonctionne**

#### Test 1.1 : Health Check
```powershell
# Ouvrir un navigateur ou utiliser curl
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

**Résultat attendu :**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "database": "connected",
  "message": "All systems operational"
}
```

#### Test 1.2 : OCR Demo
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/ocr/demo -Method POST -Body '{"text":"Facture 12345 montant 1500.50"}' -ContentType "application/json"
```

**Résultat attendu :**
- word_count: 4
- detected_numbers: ["12345", "1500.50"]

#### Test 1.3 : HS Classification
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/hs/suggest -Method POST -Body '{"product_description":"ordinateur portable"}' -ContentType "application/json"
```

**Résultat attendu :**
- suggested_codes contient des codes 8471.xx
- confidence_score > 0.70

---

### 2. **Base de Données Chiffrée Fonctionne**

#### Test 2.1 : Vérifier que la DB est créée
```powershell
Test-Path data/declado.db
# Doit retourner True
```

#### Test 2.2 : Vérifier le chiffrement
```powershell
# Essayer d'ouvrir la DB sans clé (doit échouer)
sqlite3 data/declado.db "SELECT * FROM health_checks;"
# Erreur attendue : "file is not a database"
```

#### Test 2.3 : Vérifier les écritures
```bash
# Appeler /api/health plusieurs fois
# Puis vérifier avec Python :
```

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python
```

```python
from app.db import SessionLocal
from app.db.models import HealthCheck

db = SessionLocal()
count = db.query(HealthCheck).count()
print(f"Health checks enregistrés : {count}")
# Doit être > 0
```

---

### 3. **Frontend Electron Lance Correctement**

#### Test 3.1 : Application démarre
- ✅ Fenêtre Electron s'ouvre
- ✅ Interface React s'affiche
- ✅ Pas d'erreurs dans la console

#### Test 3.2 : Communication Electron ↔ Backend
- ✅ Informations système affichées (Platform, Electron version, etc.)
- ✅ Backend URL affiché : `http://127.0.0.1:8000`

---

### 4. **Frontend Communique avec Backend**

#### Test 4.1 : Health Check depuis l'UI
1. Cliquer sur "Vérifier le Backend"
2. **Résultat attendu :**
   - Status: healthy
   - Version: 0.1.0
   - Database: connected
   - Pas d'erreur

#### Test 4.2 : OCR Demo depuis l'UI
1. Entrer du texte : `Facture N°12345 montant 1500.50 EUR`
2. Cliquer sur "Analyser le texte"
3. **Résultat attendu :**
   - Mots: 5
   - Caractères: 38
   - Nombres détectés: 12345, 1500.50

#### Test 4.3 : HS Classification depuis l'UI
1. Entrer : `ordinateur portable`
2. Cliquer sur "Suggérer code HS"
3. **Résultat attendu :**
   - Liste de codes HS affichée
   - Code 8471.xx présent
   - Pourcentages de confiance affichés

---

## 🧪 Tests Automatisés

### Tests Backend

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest -v
```

**Tests inclus :**
- ✅ test_root
- ✅ test_health_ping
- ✅ test_health_check
- ✅ test_ocr_demo
- ✅ test_hs_suggest
- ✅ Validations Pydantic

### Tests Frontend (à venir)

```powershell
cd frontend
npm test
```

### Lancer tous les tests

```powershell
.\scripts\test.ps1
```

---

## 📊 Validation des Critères d'Acceptation

### ✅ Checklist Finale

- [ ] **L'app desktop lance** : Electron démarre sans erreur
- [ ] **Backend répond** : Tous les endpoints fonctionnent
- [ ] **DB chiffrée accessible** : 
  - ✅ Uniquement via l'app (avec la clé)
  - ✅ Pas accessible directement (sans clé)
- [ ] **Communication end-to-end** : Frontend → Backend → DB fonctionne
- [ ] **Tests passent** : pytest backend réussit
- [ ] **Packaging test** : Build dev fonctionne (voir section suivante)

---

## 📦 Test de Packaging (Dev Build)

### Build Backend Standalone

```powershell
# Tester PyInstaller
cd backend
.\venv\Scripts\Activate.ps1
pyinstaller --onefile app/main.py --name declado-backend-test

# Tester l'exécutable
cd dist
.\declado-backend-test.exe
```

### Build Frontend (dev)

```powershell
cd frontend
npm run build

# Vérifier que dist/ est créé
ls dist/
```

---

## 🐛 Dépannage

### Backend ne démarre pas

```powershell
# Vérifier les logs
cd backend
.\venv\Scripts\Activate.ps1
python -m app.main
```

### Frontend ne se connecte pas au backend

1. Vérifier que le backend tourne : `http://127.0.0.1:8000`
2. Ouvrir DevTools dans Electron (F12)
3. Vérifier la console pour les erreurs

### Base de données corrompue

```powershell
# Supprimer et recréer
Remove-Item data/declado.db
cd backend
.\venv\Scripts\Activate.ps1
python -c "from app.db import init_db; init_db()"
```

### Erreur de clé de chiffrement

Vérifier `.env` :
```
DATABASE_ENCRYPTION_KEY=changeme_with_32_byte_key_here
```

---

## 📈 Métriques de Performance

### Temps de démarrage cibles :
- Backend : < 3 secondes
- Frontend : < 5 secondes
- Premier health check : < 1 seconde

### Latence cibles :
- /api/health : < 100ms
- /api/ocr/demo : < 200ms
- /api/hs/suggest : < 300ms

---

## 🎯 Prochaines Étapes

Une fois ce prototype validé :

1. ✅ **Phase 2.1** : OCR réel avec Tesseract
2. ✅ **Phase 2.2** : ML Classification HS (TF-IDF + SVM)
3. ✅ **Phase 2.3** : Calculs douaniers CEMAC
4. ✅ **Phase 2.4** : Export PDF/XML
5. ✅ **Phase 3** : Packaging production Windows

---

## 📞 Support

- **Documentation** : `README.md`, `NEXT_STEPS.md`
- **Issues** : GitHub Issues
- **Email** : dev@declado-ia.com

---

**🎉 Bon test du prototype !**
