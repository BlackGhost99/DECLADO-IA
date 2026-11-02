# Lot : contrôles croisés entre les pièces (T88, T101)

Nuit du 2 novembre 2026, après la lecture des listes de colisage et des certificats d'origine (T87).

## Fonctionnalités terminées

`apps/cases/crosschecks.py`, appelé par le contrôle de complétude : chaque écart devient un **avertissement** de l'onglet Contrôles, rattaché à la pièce (lien vers l'onglet Documents). Rien n'est bloquant : c'est à l'agent de juger.

- **Facture citée absente** : un B/L, une assurance, une facture de fret, une liste de colisage ou un certificat d'origine cite un n° de facture qui n'est pas dans le dossier (pièce d'un autre envoi, ou facture manquante).
- **Sous-assurance** : valeur assurée inférieure au total des factures, comparée seulement dans la même devise.
- **Origine** : pays du certificat d'origine différent de l'origine d'une marchandise.
- **Masses** : masse brute de la liste de colisage différente de celle du titre de transport de plus de 1 % (un seul titre et une seule liste dans le dossier).
- **Conteneurs (T101, 2 novembre 2026)** : tous les n° de conteneur imprimés (format ISO 6346) sont relevés sur les titres de transport et les listes de colisage, dans le champ lu et dans le texte de la pièce. Un conteneur de la liste de colisage absent du titre de transport est signalé sur la liste ; un conteneur du titre (un seul titre dans le dossier) absent de toutes les listes est signalé sur le titre. Le chiffre de contrôle, parfois omis, n'est pas comparé.
- **Scellés (T101)** : nouveau champ « Scellé » lu sur le titre de transport et la liste de colisage (FR/EN/ES/AR). Un écart n'est signalé que si le scellé de la liste est introuvable dans le texte du titre et inversement : un titre à plusieurs conteneurs imprime plusieurs scellés.

Une valeur inconnue des deux côtés, ou d'un seul côté, ne déclenche rien. La valeur saisie par l'agent à la place de la lecture est celle comparée.

**Origine reprise du certificat (T89)** : quand un certificat d'origine lu cite exactement le n° d'une facture du dossier, son pays est reporté sur les marchandises de cette facture qui n'ont pas d'origine, que le certificat soit lu avant ou après la facture. Une origine déjà connue n'est jamais écrasée (l'écart est alors signalé par le contrôle ci-dessus) ; deux certificats contradictoires pour la même facture, ou un certificat d'une autre facture, ne remplissent rien. Chaque report est journalisé (`goods_line.origin_from_certificate`, avec la pièce source) et reste modifiable.

Aussi : les propositions « à confirmer » nomment maintenant le bureau d'entrée et les taux de change (réglages de la société, T86).

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `tests/test_controles_croises.py` (8 tests : pièces cohérentes sans signalement, facture d'un autre envoi et masse différente, sous-assurance, origine du certificat (T88) ; origine reprise du certificat lu avant la facture, certificat d'une autre facture puis certificat conforme (T89) ; même conteneur sans chiffre de contrôle et même scellé sans signalement, autre conteneur et autre scellé signalés sans blocage (T101)).
- Suite backend complète ; frontend : typecheck, vitest, build.

## Limites

- Plusieurs titres de transport ou plusieurs listes de colisage : la comparaison des masses n'est pas faite (pas d'appariement deviné).
- L'origine reprise du certificat n'est pas marquée « à confirmer » ligne par ligne : elle est journalisée avec sa pièce source et reste modifiable.
- Scellés : un seul titre de transport dans le dossier ; le premier scellé imprimé est celui lu (les autres sont cherchés dans le texte).
- Le chiffre de contrôle ISO 6346 n'est pas vérifié (une erreur de lecture d'un seul chiffre reste possible).

## Prochaine étape

Format d'échange SYDONIA (en attente de décision) ; textes officiels des exonérations et des taxes.
