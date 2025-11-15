# ==========================================
# DECLADO-IA - Build Instructions
# ==========================================

## Vue d'ensemble

Ce document explique comment construire DECLADO-IA pour Windows.

## Prérequis

### Outils nécessaires

1. **Python 3.11** (via pyenv ou installation directe)
2. **Node.js 18.19+** (via nvm-windows ou installation directe)
3. **Windows SDK** (pour signtool.exe)
   - Télécharger : https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/
4. **Git** (pour le versioning)

### Certificat de signature (optionnel mais recommandé)

Pour éviter les alertes Windows SmartScreen, obtenir un certificat Code Signing.

## Installation des dépendances

### Backend (Python)

```powershell
# Naviguer vers le dossier backend
cd backend

# Créer un environnement virtuel
python -m venv venv

# Activer l'environnement
.\venv\Scripts\Activate.ps1

# Installer les dépendances
pip install -r requirements.txt

# Installer PyInstaller
pip install pyinstaller
```

### Frontend (Electron)

```powershell
# Naviguer vers le dossier frontend
cd frontend

# Installer les dépendances
npm install

# Ou avec Yarn
yarn install
```

## Build du Backend

```powershell
# Depuis la racine du projet
python scripts/build_backend.py
```

Le fichier `.exe` sera généré dans `dist/backend/`.

### Options avancées PyInstaller

Pour personnaliser le build, éditer `scripts/build_backend.py` :

- `--onefile` : Un seul exécutable (plus lent au démarrage)
- `--onedir` : Dossier avec dépendances (démarrage plus rapide)
- `--windowed` : Pas de console
- `--console` : Avec console (utile pour debug)

## Build du Frontend (Electron)

### Mode développement

```powershell
cd frontend

# Démarrer en mode dev avec hot-reload
npm run electron:dev
```

### Build de production

```powershell
cd frontend

# Build pour Windows
npm run electron:build:win
```

Les installateurs seront générés dans `frontend/release/`.

### Formats de sortie

Par défaut, electron-builder génère :
- **NSIS installer** : `DECLADO-IA-Setup-0.1.0-x64.exe`
- **Portable** : `DECLADO-IA-Portable-0.1.0.exe`

## Signature du code (Windows)

### Configuration

1. Placer votre certificat `.pfx` dans un dossier sécurisé
2. Configurer `secrets.json` :

```json
{
  "code_signing": {
    "certificate_path": "C:\\path\\to\\certificate.pfx",
    "certificate_password": "YOUR_PASSWORD",
    "timestamp_url": "http://timestamp.digicert.com"
  }
}
```

### Signature automatique

La signature est automatique lors du build si `secrets.json` est configuré.

Le script `scripts/sign-windows.js` est appelé par electron-builder.

### Signature manuelle

```powershell
# Avec signtool.exe
signtool sign /f "certificate.pfx" /p "password" /tr "http://timestamp.digicert.com" /td SHA256 /fd SHA256 "DECLADO-IA-Setup.exe"
```

## Build complet (Full Release)

Pour créer une release complète :

```powershell
# 1. Nettoyer les anciens builds
Remove-Item -Recurse -Force dist, build, frontend/dist, frontend/release

# 2. Build backend
python scripts/build_backend.py

# 3. Build frontend
cd frontend
npm run electron:build:win
cd ..

# 4. Les fichiers finaux sont dans :
# - frontend/release/ (Installateurs Electron)
# - dist/backend/ (Backend standalone si nécessaire)
```

## Structure du package final

```
DECLADO-IA-Setup-0.1.0-x64.exe
├── Application Electron (Frontend)
├── Backend Python (embarqué ou service séparé)
├── Tesseract OCR
├── Modèles ML (ONNX)
├── Référentiels CEMAC
└── Templates (PDF, XML)
```

## Distribution

### Options de distribution

1. **Installateur NSIS** (recommandé)
   - Installation classique Windows
   - Raccourcis bureau/menu démarrer
   - Désinstallation propre

2. **Portable**
   - Pas d'installation
   - Exécution directe
   - Utile pour tests ou USB

3. **Microsoft Store** (futur)
   - Distribution via Windows Store
   - Mises à jour automatiques

### Signature et notarisation

Pour une distribution publique :

1. ✅ Signer avec un certificat EV (Extended Validation) si possible
2. ✅ Timestamp les signatures (pour validité post-expiration certificat)
3. ✅ Tester sur machines propres (sans dev tools)
4. ✅ Soumettre à SmartScreen Reputation si nécessaire

## Mises à jour automatiques

Pour activer les auto-updates (à implémenter) :

1. Configurer un serveur de releases
2. Utiliser `electron-updater`
3. Signer toutes les releases

Voir `docs/AUTO_UPDATE.md` pour plus de détails (à créer).

## Dépannage

### Erreur : signtool.exe non trouvé

```powershell
# Installer le Windows SDK
# Ou spécifier le chemin manuellement dans sign-windows.js
```

### Erreur : Module non trouvé lors de l'exécution

```powershell
# Ajouter le module manquant dans build_backend.py
--hidden-import=nom_du_module
```

### Build trop volumineux

- Exclure les modules inutiles avec `--exclude-module`
- Utiliser `--onefile` avec compression
- Nettoyer les dépendances inutilisées

### Antivirus bloque l'exécutable

- Signer le code avec un certificat valide
- Soumettre à Microsoft Defender SmartScreen
- Ajouter exception temporaire pour tests

## Checklist avant release

- [ ] Version mise à jour dans `package.json` et `pyproject.toml`
- [ ] Tests passent (backend + frontend)
- [ ] Build sans erreurs
- [ ] Code signé
- [ ] Testé sur machine propre Windows 10/11
- [ ] Documentation à jour (README, CHANGELOG)
- [ ] Référentiels CEMAC à jour
- [ ] Certificat de signature valide (non expiré)

## Support

Pour les questions de build : dev@declado-ia.com
