# 🚀 DECLADO-IA

**Système d'Extraction Automatisée de Factures & Calculs Douaniers – Zone CEMAC**

[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18.19-green.svg)](https://nodejs.org/)
[![Electron](https://img.shields.io/badge/electron-28.1-blue.svg)](https://www.electronjs.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.109-green.svg)](https://fastapi.tiangolo.com/)

---

## 📘 Vue d'ensemble

DECLADO-IA est une application desktop Windows qui automatise l'extraction de données depuis des factures et calcule automatiquement tous les droits et taxes douaniers conformément à la réglementation CEMAC.

### ✨ Fonctionnalités principales

- 🔍 **OCR automatisé** : Extraction de texte et tableaux depuis PDF et images
- 🤖 **Classification HS intelligente** : Suggestions de codes douaniers via IA/ML
- 💰 **Calculs douaniers complets** : DD, TVA, TCI, CCI, redevances CEMAC
- 📄 **Export multi-format** : PDF, XML (eSAD), CSV/JSON
- 🔒 **Sécurité renforcée** : Base de données chiffrée (SQLCipher)
- 📡 **Fonctionnement offline-first** : Tous les traitements en local
- 🌐 **Multi-entreprises & utilisateurs** : Gestion complète des accès

---

## 🏗️ Architecture

```
DECLADO-IA/
├── backend/          # API FastAPI (Python)
│   ├── app/
│   │   ├── api/          # Endpoints REST
│   │   ├── core/         # Configuration, sécurité
│   │   ├── db/           # Modèles SQLAlchemy
│   │   ├── models/       # Schémas Pydantic
│   │   └── services/     # Logique métier
│   │       ├── ocr/      # Tesseract + OpenCV
│   │       ├── ml/       # Classification HS
│   │       └── tax_engine/ # Calculs douaniers
│   └── tests/
├── frontend/         # Application Electron + React
│   ├── src/
│   │   ├── components/   # Composants React
│   │   ├── pages/        # Pages principales
│   │   ├── services/     # API calls
│   │   └── store/        # State management (Zustand)
│   └── electron/         # Process Electron
├── ml/               # Machine Learning
│   ├── training/         # Scripts d'entraînement
│   ├── models/           # Modèles ONNX
│   └── data/             # Datasets
├── data/             # Données (versionnées avec DVC)
│   ├── raw/              # Factures brutes
│   ├── processed/        # Données traitées
│   ├── exports/          # Exports générés
│   └── referentials/     # SH, TEC, taux BEAC
├── docs/             # Documentation
├── scripts/          # Scripts de build
└── tests/            # Tests d'intégration
```

---

## 🚀 Démarrage rapide

### Prérequis

- **Windows 10/11** (64-bit)
- **Python 3.11** ([pyenv-win](https://github.com/pyenv-win/pyenv-win) recommandé)
- **Node.js 18.19+** ([nvm-windows](https://github.com/coreybutler/nvm-windows) recommandé)
- **Tesseract OCR** ([installation](https://github.com/UB-Mannheim/tesseract/wiki))
- **Git** ([Git for Windows](https://git-scm.com/download/win))

### Installation

```powershell
# 1. Cloner le dépôt
git clone https://github.com/votre-org/declado-ia.git
cd declado-ia

# 2. Copier les fichiers de configuration
cp .env.example .env
cp secrets.example.json secrets.json

# 3. Configurer les secrets (éditer .env et secrets.json)
notepad .env

# 4. Backend Python
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 5. Frontend Node/Electron
cd ..\frontend
npm install

# 6. Pre-commit hooks (optionnel)
cd ..
pip install pre-commit
pre-commit install
```

### Configuration de Tesseract

```powershell
# Installer Tesseract OCR depuis :
# https://github.com/UB-Mannheim/tesseract/wiki

# Dans .env, configurer le chemin :
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### Lancement en développement

```powershell
# Terminal 1 - Backend API
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2 - Frontend Electron
cd frontend
npm run electron:dev
```

L'application Electron se lance avec hot-reload activé.

---

## 📦 Build & Packaging

### Build de production

```powershell
# Backend (exécutable PyInstaller)
python scripts/build_backend.py

# Frontend (installateur Windows)
cd frontend
npm run electron:build:win
```

Les fichiers sont générés dans :
- `frontend/release/` : Installateurs NSIS et portable
- `dist/backend/` : Backend standalone (si nécessaire)

### Signature du code

Pour signer les builds Windows :

1. Obtenir un certificat Code Signing
2. Configurer `secrets.json` :

```json
{
  "code_signing": {
    "certificate_path": "C:\\path\\to\\cert.pfx",
    "certificate_password": "YOUR_PASSWORD"
  }
}
```

Voir [`docs/BUILD.md`](docs/BUILD.md) pour plus de détails.

---

## 🧪 Tests

```powershell
# Tests Backend (Pytest)
cd backend
pytest

# Avec coverage
pytest --cov=app --cov-report=html

# Tests Frontend (Vitest)
cd frontend
npm test

# Tests avec UI
npm run test:ui
```

---

## 📚 Documentation

- **[Guide de démarrage](docs/GETTING_STARTED.md)** (à créer)
- **[Architecture technique](docs/ARCHITECTURE.md)** (à créer)
- **[Configuration DVC](docs/DVC_SETUP.md)**
- **[Gestion des secrets](docs/SECRETS_MANAGEMENT.md)**
- **[Instructions de build](docs/BUILD.md)**
- **[API Documentation](docs/API.md)** (à créer)

---

## 🔧 Outils & Technologies

### Backend
- **FastAPI** : Framework API REST
- **SQLAlchemy** : ORM pour base de données
- **SQLCipher** : Chiffrement base de données
- **Tesseract** : OCR open-source
- **OpenCV** : Traitement d'images
- **scikit-learn** : Classification ML
- **ONNX Runtime** : Inférence modèles ML

### Frontend
- **Electron** : Application desktop
- **React 18** : UI framework
- **TypeScript** : Typage statique
- **Vite** : Build tool
- **Zustand** : State management
- **TanStack Query** : Data fetching

### DevOps
- **DVC** : Versioning données & modèles ML
- **MLflow** : Tracking expériences ML
- **Pre-commit** : Hooks qualité code
- **Black/Ruff** : Formatage Python
- **ESLint/Prettier** : Formatage JavaScript

---

## 🤝 Contribution

### Workflow Git

```bash
# Créer une branche feature
git checkout -b feature/ma-fonctionnalite

# Faire vos modifications et commits
git add .
git commit -m "feat: ajouter fonctionnalité X"

# Pousser et créer une PR
git push origin feature/ma-fonctionnalite
```

### Conventions de commits

Utiliser [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat:` Nouvelle fonctionnalité
- `fix:` Correction de bug
- `docs:` Documentation
- `style:` Formatage code
- `refactor:` Refactoring
- `test:` Tests
- `chore:` Tâches de maintenance

### Standards de code

```powershell
# Formater le code Python
black backend/

# Linter Python
ruff check backend/

# Formater le code TypeScript
cd frontend
npm run format

# Linter TypeScript
npm run lint
```

Les pre-commit hooks vérifient automatiquement ces standards.

---

## 📊 Roadmap

### Phase 1 - MVP (8-10 semaines) ✅
- [x] Setup projet
- [ ] OCR de base + extraction
- [ ] Classification HS (TF-IDF + SVM)
- [ ] Calculs douaniers CEMAC
- [ ] Interface Electron basique
- [ ] Export PDF

### Phase 2 - Améliorations (8-12 semaines)
- [ ] Documents requis automatiques
- [ ] Export XML eSAD
- [ ] Multi-utilisateurs
- [ ] Historique & recherche
- [ ] Modèles OCR par fournisseur

### Phase 3 - ML Avancé (12-16 semaines)
- [ ] Modèle transformer (ONNX)
- [ ] Questions dynamiques
- [ ] Interface web supervision
- [ ] Connecteurs ERP/WMS

---

## 🐛 Support & Issues

- **Bugs** : [GitHub Issues](https://github.com/votre-org/declado-ia/issues)
- **Support** : support@declado-ia.com
- **Sécurité** : security@declado-ia.com

---

## 📄 Licence

Copyright © 2025 DECLADO-IA. Tous droits réservés.

Ce logiciel est propriétaire. Toute utilisation, reproduction ou distribution non autorisée est strictement interdite.

---

## 👥 Équipe

- **Chef de Projet** : [Nom]
- **Lead Dev Backend** : [Nom]
- **Lead Dev Frontend** : [Nom]
- **ML Engineer** : [Nom]

---

## 🙏 Remerciements

- Communauté Tesseract OCR
- FastAPI & Electron communities
- Zone CEMAC pour les référentiels douaniers

---

**Made with ❤️ for CEMAC Customs**
