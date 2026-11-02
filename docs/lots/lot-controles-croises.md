# Lot : contrôles croisés entre les pièces (T88)

Nuit du 2 novembre 2026, après la lecture des listes de colisage et des certificats d'origine (T87).

## Fonctionnalités terminées

`apps/cases/crosschecks.py`, appelé par le contrôle de complétude : chaque écart devient un **avertissement** de l'onglet Contrôles, rattaché à la pièce (lien vers l'onglet Documents). Rien n'est bloquant : c'est à l'agent de juger.

- **Facture citée absente** : un B/L, une assurance, une facture de fret, une liste de colisage ou un certificat d'origine cite un n° de facture qui n'est pas dans le dossier (pièce d'un autre envoi, ou facture manquante).
- **Sous-assurance** : valeur assurée inférieure au total des factures, comparée seulement dans la même devise.
- **Origine** : pays du certificat d'origine différent de l'origine d'une marchandise.
- **Masses** : masse brute de la liste de colisage différente de celle du titre de transport de plus de 1 % (un seul titre et une seule liste dans le dossier).

Une valeur inconnue des deux côtés, ou d'un seul côté, ne déclenche rien. La valeur saisie par l'agent à la place de la lecture est celle comparée.

Aussi : les propositions « à confirmer » nomment maintenant le bureau d'entrée et les taux de change (réglages de la société, T86).

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `tests/test_controles_croises.py` (4 tests : pièces cohérentes sans signalement, facture d'un autre envoi et masse différente, sous-assurance, origine du certificat).
- Suite backend complète ; frontend : typecheck, vitest, build.

## Limites

- Plusieurs titres de transport ou plusieurs listes de colisage : la comparaison des masses n'est pas faite (pas d'appariement deviné).
- Le pays du certificat d'origine n'est pas reporté sur les marchandises : il est seulement comparé.
- Le conteneur cité par chaque pièce n'est pas encore comparé.

## Prochaine étape

Proposer l'origine des marchandises depuis un certificat d'origine rattaché à la facture (à confirmer par l'agent).
