# Lot : réglages de préparation de la société (T86)

Suite des lots 7 (préparation automatique) et 9 (taux de change par dossier). Nuit du 2 novembre 2026.

## Fonctionnalités terminées

- **Administration › Préparation des dossiers** (nouvel onglet, composants existants : carte, tableau, formulaire).
  - Régime et bureau d'entrée par défaut : visibles par tous, modifiés par l'administrateur de la société (`PUT /api/v1/organization/preparation-settings`).
  - Cours de change de la société : devise, cours en FCFA, date d'effet, source obligatoire ; ajout seul, l'historique reste ; saisis par un validateur ou l'administrateur (`/api/v1/organization/exchange-rates`). XAF et EUR refusés (parité fixe).
- **Préparation automatique** (après la lecture d'une facture), seulement dans les champs vides et marqués « à confirmer » :
  - régime : celui de la société, sinon celui du dernier dossier (comme avant) ;
  - bureau d'entrée : celui de la société ;
  - taux de change de chaque devise facturée : le cours de la société en vigueur à la date de déclaration prévue, avec la source « Cours de la société au JJ/MM/AAAA (source) ». Un cours futur n'est pas appliqué avant sa date.
  - Un taux déjà saisi dans le dossier n'est jamais remplacé. Dans l'onglet Calculs, le bloc des taux signale le taux proposé ; enregistré par l'agent, il n'est plus une proposition.
- Journal : `organization.preparation_settings_updated`, `organization.exchange_rate_added` ; les propositions passent par `revision.prepared_automatically`.
- Onglet Calculs, « Nombre de colis » : repris des titres de transport lus (T85).

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

Migration : `cases/0013_reglages_preparation_cours` (deux tables, aucune donnée modifiée).

## Tests exécutés

- Backend : `tests/test_reglages_preparation.py` (4 tests : droits, validation, isolation, proposition au cours en vigueur, pas d'écrasement, cours futur ignoré) et `tests/test_preparation_auto.py` inchangé et vert.
- Frontend : `tests/Preparation.test.tsx` (lecture seule pour un déclarant, ajout d'un cours par un validateur), suite complète et build.

## Limites

- Un cours ne se corrige pas : on en saisit un nouveau (date d'effet identique, le plus récent l'emporte).
- Les devises des pièces de fret et d'assurance ne reçoivent pas encore de proposition : seule la devise des factures.
- Pas d'import de cours depuis un fichier BEAC : saisie manuelle, volontairement (jamais téléchargé).

## Prochaine étape

Rattacher la liste de colisage et le certificat d'origine par n° de facture dans le dépôt groupé.
