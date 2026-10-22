# Lot 0 — Socle : compte rendu de livraison

Date : 6 octobre 2026. Backlog couvert : DEV-001 à DEV-004 (`docs/specifications/03-plan-et-recette.md`).

## Fonctionnalités réellement terminées

- **Dépôt démarrable** : backend Django 5.2 LTS + DRF, PostgreSQL, Celery/Redis configurés ; frontend React/TypeScript (Vite) ; Docker Compose ; versions verrouillées.
- **Comptes et sociétés** (DEV-002) : utilisateur à identité globale (e-mail), sociétés, affiliations avec rôles cumulables (déclarant, validateur, administrateur de société), gestionnaire du référentiel comme permission distincte hors société. Session serveur, cookie HttpOnly (Secure hors développement), CSRF obligatoire, y compris sur la connexion.
- **Société active** : dérivée de la session et d'une affiliation active ; sélection explicite si plusieurs affiliations ; un `organization_id` envoyé par le client est ignoré.
- **Isolation** (DEV-003) : toutes les lectures métier passent par `for_organization()`. Un objet d'une autre société répond 404, indiscernable d'un identifiant inexistant.
- **Désactivation** (ACC-03) : affiliation désactivée par l'administrateur de société ou compte désactivé globalement ; accès coupé à la requête suivante, historique conservé et attribué. Garde-fous : pas d'auto-désactivation, au moins un administrateur actif.
- **Importateurs** (socle de CLI-01) : création, modification avec verrou optimiste (`row_version` ou `If-Match`, 409 si périmé), doublons possibles signalés sans fusion, identifiants conservés en texte (zéros initiaux).
- **Journal** (DEV-004, AUD-01/02 socle) : `AuditEvent` append-only, protégé côté ORM et par déclencheur PostgreSQL ; avant/après, acteur, request_id ; consultation filtrée par acteur, type et période, bornée à la société.
- **Outbox** : événements enregistrés dans la transaction métier, distribution idempotente par worker, tentatives bornées et erreurs visibles.
- **Erreurs structurées** : `{code, message, details, request_id}`, 401/403/404/409 conformes au §11 de la conception.
- **CI** : style (ruff), migrations à jour et applicables, tests backend sur PostgreSQL 16, typage, tests et build frontend.

## Commandes de démarrage

Voir le [README](../../README.md#démarrage-rapide-machine-locale).

## Tests exécutés et résultats (6 octobre 2026, Python 3.13.16, PostgreSQL 16, Node 22.22)

| Commande | Résultat |
|---|---|
| `python -m pytest` (backend) | 44 réussis, 0 échec |
| `ruff check .` / `ruff format --check .` | OK |
| `python manage.py makemigrations --check --dry-run` | aucune migration manquante |
| `python manage.py migrate` sur base vide | OK |
| `npm run typecheck` / `npm test` / `npm run build` | OK, 3 tests réussis |
| Parcours réel via le proxy Vite (connexion multi-sociétés, choix de société, liste isolée) | OK, captures dans le compte rendu de la conversation |
| `docker compose config` | fichier valide |
| `docker compose up --build` | **non vérifié** : l'environnement de développement a reçu un refus de Docker Hub (429, limite de téléchargement) |

Correspondance avec la recette : T01 (partie socle : listes, détails, recherche, membres, journal ; documents et tâches arrivent aux lots 2–3), T02 complet, T33 (partie socle sur l'importateur).

## Limites connues

- Pas encore de dossiers, pièces, extraction, référentiel ni calcul : lots 1 à 5.
- La CI n'a pas tourné sur GitHub : aucun dépôt distant n'est encore configuré.
- Gestion des membres par API uniquement (pas d'écran d'ajout/désactivation dans l'interface au lot 0) ; l'interface affiche la liste pour l'administrateur.
- Pas de réinitialisation de mot de passe par e-mail (pas de service d'envoi configuré).
- Pas de limitation de débit sur la connexion ; à ajouter avant toute exposition publique.
- RLS PostgreSQL non activée (option de défense en profondeur prévue §5, non requise au lot 0).
- Le contrat OpenAPI n'est pas encore généré (prévu avec les endpoints du lot 2).

## Prochaine étape

Lot 1 (référentiel). Il nécessite les sources : PDF CEMAC 2009 (551 pages), Excel « 2016 » (5 609 codes) et `audit-et-conception.md`. Sans elles, le lot 1 avance uniquement sur le jeu synthétique F (parents, « autres », notes, code invalide, doublon, dates divergentes). Le lot 2 (dossiers et pièces) peut démarrer en parallèle.
