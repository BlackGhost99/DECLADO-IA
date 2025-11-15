# ✅ SETUP INITIAL TERMINÉ !

## 🎉 Ce qui a été fait

✅ **Git configuré et initialisé**
- Dépôt Git créé avec commit initial
- Branches `main` et `develop` créées
- Configuration utilisateur : "DECLADO-IA Team"
- 40 fichiers commités avec succès

✅ **Structure complète du projet**
- Backend Python/FastAPI
- Frontend Electron/React
- Configuration ML avec DVC
- Scripts de build et déploiement

✅ **Configuration qualité code**
- Linters : Black, Ruff, ESLint, Prettier
- Pre-commit hooks configurés
- EditorConfig pour cohérence

✅ **Fichiers de configuration créés**
- `.env` (à personnaliser)
- `secrets.json` (à personnaliser)
- `.vscode/settings.json`

---

## 📋 PROCHAINES ÉTAPES

### 1. ⚙️ Installer Python 3.11

Si pas déjà installé :

```powershell
# Vérifier la version
python --version

# Si Python n'est pas installé ou version < 3.11
winget install Python.Python.3.11
```

Puis **redémarrer PowerShell**.

### 2. 🐍 Créer l'environnement virtuel Python

```powershell
# Aller dans le dossier backend
cd backend

# Créer l'environnement virtuel
python -m venv venv

# Activer l'environnement
.\venv\Scripts\Activate.ps1

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt

# Revenir à la racine
cd ..
```

### 3. 📦 Installer Node.js et les dépendances frontend

Si Node.js n'est pas installé :

```powershell
# Vérifier la version
node --version

# Si pas installé ou version < 18
winget install OpenJS.NodeJS.LTS
```

Puis **redémarrer PowerShell** et :

```powershell
# Aller dans le dossier frontend
cd frontend

# Installer les dépendances
npm install

# Revenir à la racine
cd ..
```

### 4. 🔧 Installer Tesseract OCR

Télécharger et installer depuis :
https://github.com/UB-Mannheim/tesseract/wiki

Puis configurer dans `.env` :
```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### 5. 🎨 Configurer les secrets

Éditer les fichiers créés :

```powershell
# Ouvrir .env
notepad .env

# Ouvrir secrets.json
notepad secrets.json
```

**Générer des clés sécurisées :**

```powershell
# PowerShell - Générer une clé de 32 caractères
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

### 6. 🪝 Installer les pre-commit hooks

```powershell
# Activer l'environnement virtuel backend d'abord
cd backend
.\venv\Scripts\Activate.ps1

# Installer pre-commit
pip install pre-commit

# Installer les hooks
pre-commit install

# Tester (optionnel)
pre-commit run --all-files
```

### 7. 🚀 Tester le lancement

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

### 8. 🧪 Lancer les tests

**Backend :**
```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest
```

**Frontend :**
```powershell
cd frontend
npm test
```

---

## 🔗 Connexion à GitHub/GitLab (Optionnel)

```powershell
# 1. Créer un nouveau dépôt sur GitHub/GitLab

# 2. Ajouter le remote
git remote add origin https://github.com/votre-org/declado-ia.git

# 3. Pousser le code
git push -u origin main
git push -u origin develop
```

---

## 📚 Documentation disponible

- `README.md` - Vue d'ensemble et quickstart
- `docs/BUILD.md` - Instructions de build
- `docs/DVC_SETUP.md` - Configuration DVC
- `docs/SECRETS_MANAGEMENT.md` - Gestion des secrets
- `CONTRIBUTING.md` - Guide de contribution
- `GIT_SETUP.md` - Configuration Git

---

## 🆘 Commandes utiles

```powershell
# Voir le statut Git
git status

# Voir les branches
git branch -a

# Voir l'historique
git log --oneline --graph --all

# Créer une nouvelle branche feature
git checkout -b feature/ma-fonctionnalite

# Activer l'environnement Python
.\backend\venv\Scripts\Activate.ps1

# Formater le code Python
cd backend
black app/

# Formater le code TypeScript
cd frontend
npm run format
```

---

## ✨ Helpers PowerShell

Un fichier `scripts/powershell-profile.ps1` a été créé avec des aliases utiles.

Pour l'utiliser automatiquement, ajoutez à votre profil PowerShell :

```powershell
# Éditer le profil PowerShell
notepad $PROFILE

# Ajouter cette ligne :
. C:\Users\BlackGhost\Desktop\DECLADO-IA\scripts\powershell-profile.ps1
```

---

## 🎯 Checklist de vérification

- [ ] Python 3.11 installé
- [ ] Environnement virtuel créé (`backend/venv`)
- [ ] Dépendances Python installées
- [ ] Node.js 18+ installé
- [ ] Dépendances Node installées
- [ ] Tesseract OCR installé
- [ ] Fichiers `.env` et `secrets.json` configurés
- [ ] Pre-commit hooks installés
- [ ] Backend démarre sans erreur
- [ ] Frontend démarre sans erreur

---

**🎉 Félicitations ! Le setup initial est terminé !**

Pour toute question : contact@declado-ia.com
