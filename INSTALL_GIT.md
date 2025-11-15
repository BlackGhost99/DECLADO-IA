# ==========================================
# DECLADO-IA - Installation Git pour Windows
# ==========================================

## ⚠️ Git n'est pas installé

Vous devez installer Git pour Windows avant de continuer.

## Installation rapide

### Option 1 : Téléchargement direct (Recommandé)

1. **Télécharger Git for Windows**
   - Lien : https://git-scm.com/download/win
   - Le téléchargement démarrera automatiquement

2. **Installer avec les options par défaut**
   - Double-cliquer sur le fichier téléchargé
   - Suivre l'assistant d'installation
   - **IMPORTANT** : Cocher "Git from the command line and also from 3rd-party software"

3. **Redémarrer PowerShell**
   - Fermer toutes les fenêtres PowerShell
   - Ouvrir une nouvelle fenêtre PowerShell
   - Tester : `git --version`

### Option 2 : Avec winget (Windows Package Manager)

Si vous avez winget installé :

```powershell
winget install --id Git.Git -e --source winget
```

Puis redémarrer PowerShell.

### Option 3 : Avec Chocolatey

Si vous avez Chocolatey installé :

```powershell
choco install git -y
```

Puis redémarrer PowerShell.

## Après l'installation

### 1. Vérifier l'installation

```powershell
# Redémarrer PowerShell puis :
git --version
# Devrait afficher : git version 2.x.x
```

### 2. Configuration initiale

```powershell
# Configurer votre nom
git config --global user.name "Votre Nom"

# Configurer votre email
git config --global user.email "votre.email@example.com"

# Configurer l'éditeur par défaut (optionnel)
git config --global core.editor "code --wait"  # Pour VS Code

# Vérifier la configuration
git config --list
```

### 3. Initialiser le dépôt DECLADO-IA

```powershell
# Dans le dossier du projet
cd C:\Users\BlackGhost\Desktop\DECLADO-IA

# Initialiser Git
git init

# Ajouter tous les fichiers
git add .

# Premier commit
git commit -m "chore: initial project setup with complete configuration"

# Créer la branche develop
git branch develop

# Lister les branches
git branch -a
```

## Vérification de l'installation

Après avoir installé Git et redémarré PowerShell, exécutez :

```powershell
# Vérifier Git
git --version

# Vérifier la configuration
git config --global --list
```

## Problèmes courants

### Git n'est toujours pas reconnu après installation

1. **Redémarrer PowerShell** (très important !)
2. Vérifier que Git est dans le PATH :
   ```powershell
   $env:Path -split ';' | Select-String git
   ```
3. Si Git n'est pas dans le PATH, ajouter manuellement :
   ```powershell
   # Ajouter temporairement
   $env:Path += ";C:\Program Files\Git\cmd"
   
   # Pour ajouter de façon permanente, utiliser les variables d'environnement système
   ```

### Impossible de commit

Si vous obtenez une erreur du type "Please tell me who you are" :

```powershell
git config --global user.name "Votre Nom"
git config --global user.email "votre.email@example.com"
```

## Prochaines étapes après installation Git

1. ✅ Installer Git
2. ✅ Redémarrer PowerShell
3. ✅ Configurer Git (nom, email)
4. ✅ Initialiser le dépôt : `git init`
5. ✅ Premier commit : `git add . && git commit -m "chore: initial setup"`
6. ✅ Installer Python et créer l'environnement virtuel
7. ✅ Installer Node.js et les dépendances frontend
8. ✅ Installer pre-commit hooks

## Alternatives si vous ne pouvez pas installer Git maintenant

Si vous ne pouvez pas installer Git immédiatement, vous pouvez :

1. **Continuer le développement** sans versioning (déconseillé)
2. **Utiliser GitHub Desktop** (interface graphique, plus simple)
   - Télécharger : https://desktop.github.com/
3. **Utiliser VS Code Source Control** (nécessite quand même Git installé)

## Support

Pour toute question sur l'installation de Git :
- Documentation officielle : https://git-scm.com/book/fr/v2
- Support DECLADO-IA : dev@declado-ia.com

---

**⚠️ ACTION REQUISE : Installez Git puis redémarrez PowerShell avant de continuer**
