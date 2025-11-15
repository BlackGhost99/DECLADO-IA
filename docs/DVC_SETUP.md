# ==========================================
# DECLADO-IA - DVC Setup Instructions
# ==========================================

Ce fichier explique comment initialiser et utiliser DVC pour le versioning des données et modèles ML.

## Installation de DVC

```bash
pip install dvc
```

## Initialisation DVC (à faire une seule fois)

```bash
# Dans le dossier racine du projet
dvc init

# Configurer un remote local (stockage des données versionnées)
dvc remote add -d local_storage C:\DECLADO-IA-Data

# Ou utiliser un dossier réseau/NAS
# dvc remote add -d local_storage \\server\share\DECLADO-IA-Data

# Ou configurer un remote cloud (S3, Azure Blob, GCS, etc.)
# dvc remote add -d s3_storage s3://my-bucket/declado-ia
```

## Ajouter des données à DVC

```bash
# Ajouter un dossier de données
dvc add data/raw

# Ajouter des modèles ML
dvc add ml/models

# Committer les fichiers .dvc générés
git add data/raw.dvc ml/models.dvc .gitignore
git commit -m "Track data and models with DVC"

# Pousser les données vers le remote
dvc push
```

## Récupérer les données (nouveau développeur)

```bash
# Cloner le dépôt Git
git clone <repo-url>

# Configurer le remote DVC (si pas déjà fait)
dvc remote add -d local_storage C:\DECLADO-IA-Data

# Télécharger les données versionnées
dvc pull
```

## Mettre à jour des données

```bash
# Modifier les données
# ...

# Mettre à jour le tracking DVC
dvc add data/raw

# Committer les changements
git add data/raw.dvc
git commit -m "Update raw data"

# Pousser les nouvelles données
dvc push
```

## Structure recommandée pour le remote local

```
C:\DECLADO-IA-Data\
├── cache\          # Cache DVC (géré automatiquement)
├── data\
│   ├── raw\        # Données brutes
│   └── processed\  # Données traitées
└── models\         # Modèles ML
```

## Commandes utiles

```bash
# Voir le statut DVC
dvc status

# Lister les remotes configurés
dvc remote list

# Voir les fichiers trackés
dvc list . --dvc-only

# Checkout une version spécifique
git checkout <commit>
dvc checkout
```

## Important

- **Ne JAMAIS** committer les vrais fichiers de données dans Git
- Toujours committer les fichiers `.dvc` et `.dvcignore`
- Configurer le remote DVC avant de faire `dvc pull`
- Faire `dvc push` après chaque `dvc add`
