# ==========================================
# DECLADO-IA - Instructions Git
# ==========================================

## Initialisation Git (à faire manuellement)

### Si Git n'est pas installé

Télécharger et installer Git for Windows :
https://git-scm.com/download/win

### Initialisation du dépôt

```powershell
# 1. Initialiser le dépôt Git
git init

# 2. Configurer votre identité
git config user.name "Votre Nom"
git config user.email "votre.email@example.com"

# 3. Créer le premier commit
git add .
git commit -m "chore: initial project setup with complete configuration"

# 4. Créer la branche develop
git branch develop

# 5. Lister les branches
git branch
```

### Connexion à un dépôt distant (GitHub/GitLab)

```powershell
# 1. Créer un nouveau dépôt sur GitHub/GitLab (via interface web)

# 2. Ajouter le remote
git remote add origin https://github.com/votre-org/declado-ia.git

# Ou avec SSH
git remote add origin git@github.com:votre-org/declado-ia.git

# 3. Pousser le code
git push -u origin main

# 4. Pousser la branche develop
git push -u origin develop
```

### Workflow de développement

```powershell
# 1. Créer une branche feature
git checkout -b feature/nom-fonctionnalite

# 2. Faire vos modifications
# ... éditer des fichiers ...

# 3. Commit avec pre-commit hooks
git add .
git commit -m "feat: ajouter fonctionnalité X"

# 4. Pousser la branche
git push -u origin feature/nom-fonctionnalite

# 5. Créer une Pull Request sur GitHub/GitLab
```

### Installer les pre-commit hooks

```powershell
# Installer pre-commit (si pas déjà fait)
pip install pre-commit

# Installer les hooks Git
pre-commit install

# Tester les hooks
pre-commit run --all-files
```

## Structure des branches

- `main` : Production, code stable uniquement
- `develop` : Branche de développement principal
- `feature/*` : Nouvelles fonctionnalités
- `fix/*` : Corrections de bugs
- `hotfix/*` : Correctifs urgents pour production

## Commandes Git utiles

```powershell
# Voir le statut
git status

# Voir l'historique
git log --oneline --graph --all

# Changer de branche
git checkout develop

# Mettre à jour depuis remote
git pull

# Annuler des modifications non commitées
git checkout -- fichier.py

# Voir les différences
git diff

# Créer un tag de version
git tag -a v0.1.0 -m "Version 0.1.0"
git push origin v0.1.0
```

## Fichiers déjà créés

✅ `.gitignore` - Fichiers à ignorer
✅ `.gitattributes` - Gestion des fins de ligne
✅ `.pre-commit-config.yaml` - Hooks de qualité code

## Prochaines étapes

1. ✅ Installer Git (si pas déjà fait)
2. ✅ Initialiser le dépôt : `git init`
3. ✅ Premier commit : `git add . && git commit -m "chore: initial setup"`
4. ✅ Créer dépôt distant (GitHub/GitLab)
5. ✅ Pousser le code : `git push -u origin main`
6. ✅ Installer pre-commit : `pip install pre-commit && pre-commit install`

## Support

Questions Git : dev@declado-ia.com
