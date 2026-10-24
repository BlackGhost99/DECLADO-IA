# ClairTransit

Application web de préparation des dossiers douaniers pour les sociétés de transit (périmètre initial Gabon/CEMAC).
Les spécifications V1 sont dans [`docs/specifications/`](docs/specifications/). État actuel : **lots 0 (socle), 1 (référentiel), 2 (dossiers et pièces) et 3 (extraction et aide au classement)** livrés,
voir [`docs/lots/`](docs/lots/).

Un dossier « validé » dans ClairTransit signifie validé en interne par la société de transit, jamais accepté par la Douane.

## Pile technique

| Élément | Version verrouillée |
|---|---|
| Python / Django (LTS) / DRF | 3.13 / 5.2.18 / 3.18.1 |
| PostgreSQL | 16 (17 compatible) |
| Celery / Redis | 5.6.3 / Redis 7 |
| Node / React / Vite / TypeScript | 22.22+ ou 24 / 19.3.0 / 8.3.3 / 6.0.3 |

Versions Python : `backend/requirements.txt` (directes) et `backend/requirements.lock` (complètes). Node : `frontend/package-lock.json`.

## Démarrage rapide (machine locale)

Prérequis : Python 3.13, Node 22.22+ (ou 24), PostgreSQL 16, Redis, et Tesseract pour l'OCR (`apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng`, facultatif : sans lui, l'OCR échoue proprement).

```bash
# 1. Base de données (une fois)
sudo -u postgres psql -c "CREATE ROLE clairtransit LOGIN PASSWORD 'clairtransit' CREATEDB;"
sudo -u postgres createdb -O clairtransit clairtransit

# 2. API
cd backend
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo          # deux sociétés fictives + comptes de test
python manage.py runserver 127.0.0.1:8000

# 3. Interface (autre terminal)
cd frontend
npm ci
npm run dev                          # http://127.0.0.1:5173
```

Worker (nécessaire dès le lot 3 pour les extractions) : `cd backend && celery -A config worker -B -l info` (`-B` relance la boîte d'envoi toutes les 30 s).

## Démarrage avec Docker

```bash
docker compose -f infra/compose.yaml up --build
docker compose -f infra/compose.yaml exec backend python manage.py seed_demo
```

Interface : http://127.0.0.1:5173 — API : http://127.0.0.1:8000/api/v1/health — administration : http://127.0.0.1:8000/admin/.

## Comptes de démonstration

Créés par `seed_demo` (refusé hors `DJANGO_DEBUG=true`). Mot de passe commun : `demo-ClairTransit-2026`
(modifiable via `--password` ou `DEMO_PASSWORD`). Il ne protège que des données fictives ; ne jamais le réutiliser.

| Compte | Société | Rôles |
|---|---|---|
| declarant@alpha.demo | Transit Alpha (démo) | Déclarant |
| validateur@alpha.demo | Transit Alpha (démo) | Validateur |
| admin@alpha.demo | Transit Alpha (démo) | Administrateur |
| declarant@beta.demo | Transit Bêta (démo) | Déclarant |
| validateur@beta.demo | Transit Bêta (démo) | Validateur |
| admin@beta.demo | Transit Bêta (démo) | Administrateur + Déclarant |
| multi@demo.demo | les deux | Déclarant (choix de la société à la connexion) |
| referentiel@demo.demo | aucune | Gestionnaire du référentiel (import, anomalies, publication) |

`seed_demo` crée aussi un dossier fictif pour Transit Alpha : une facture PDF synthétique et une ligne « HS Code 0101.10.00 »,
prêtes à contrôler dans l'onglet Dossiers. Lancez-le après avoir publié une édition pour qu'elle soit présélectionnée
(sinon, choisissez l'édition dans le dossier).

Pour un compte d'administration technique : `python manage.py createsuperuser`. Il n'ouvre aucun accès métier aux sociétés.

## Charger un référentiel

Les sources tarifaires ne sont pas dans le dépôt. Avec le jeu synthétique F :

```bash
cd backend
python manage.py import_tariff_csv ../fixtures/synthetic/referentiel-f.csv --label "Jeu F (CSV fictif)"
python manage.py import_tariff_text ../fixtures/synthetic/referentiel-f.txt --label "Jeu F (texte fictif)"
```

Puis publier pour consultation en tant que `referentiel@demo.demo` (`POST /api/v1/tariffs/editions/<id>/publish`,
`{"mode": "consultation"}`). Classeur .xlsx original : `python manage.py import_tariff_xlsx <fichier.xlsx> --label "…"`. Commandes pour les sources réelles : [`docs/lots/lot-1.md`](docs/lots/lot-1.md).

## Vérifications

```bash
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

La CI GitHub Actions (`.github/workflows/ci.yml`) exécute les mêmes commandes avec PostgreSQL 16.

## Organisation du dépôt

```text
backend/            API Django/DRF
  config/           réglages, URL, Celery
  apps/core/        modèles de base, erreurs structurées, request_id, outbox
  apps/accounts/    utilisateurs (identité globale)
  apps/organizations/ sociétés, affiliations, rôles, société active
  apps/clients/     importateurs (socle CLI-01)
  apps/audit/       journal append-only
  apps/tariffs/     référentiel tarifaire versionné (imports, recherche, anomalies)
  tests/            tests d'API, d'isolation et de droits
frontend/           React/TypeScript (Vite)
infra/compose.yaml  environnement de développement complet
docs/               spécifications, décisions (ADR), lots, exploitation
fixtures/synthetic/ jeux de données fictifs
```

## Intelligence documentaire (bloc 4)

Le module documentaire reconstitue des **propositions d'expéditions** et de relations
plusieurs-à-plusieurs entre pièces et factures, sans double comptage ni validation automatique.
Les agents confirment ou rejettent les liens dans le détail d'un dossier.
L'analyse se fonde sur des références explicites des dernières extractions réussies.

**Attention :** l'IA externe reste désactivée, le rapprochement s'appuie sur des règles
conservatrices et les résultats ne valent pas déclaration acceptée par la Douane.
Voir [la recette et les limites](docs/lots/lot-ai-document-intelligence.md).
