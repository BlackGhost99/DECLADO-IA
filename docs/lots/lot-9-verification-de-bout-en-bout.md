# Lot 9 : vérification de bout en bout (nuit du 30 au 31 octobre 2026)

Parcours rejoué sur une facture fictive en USD (EquaTech, CIF Owendo) : import du tarif depuis l'écran,
création du dossier, lecture, marchandises, codes, calcul, validation interne, export. Recette T81.

## Corrigé

- **Fret « inclus »** : une ligne « Freight included USD 1 850 » était comptée comme un frais. Elle créait un
  faux écart de total et gonflait la valeur en douane. Elle est maintenant affichée parmi les montants non
  additionnés (`RowKind.INCLUDED`).
- **Contrôles sans doublon** : la liste passait de 26 à 12 points sur le même dossier.
  - Le code est signalé une seule fois, sur la marchandise. Ce point est bloquant, comme côté serveur.
  - L'écart de total et l'édition de consultation n'apparaissent plus deux fois.
  - La réf. fournisseur absente (facultative) n'est plus signalée. L'origine d'une ligne ne l'est plus quand le dossier en a une.
  - Chaque point « À vérifier » nomme son champ.
- **Taux de change** : une facture en USD ne pouvait jamais être calculée, faute d'endroit où saisir le taux.
  - L'onglet Calculs demande le taux des devises sans parité fixe (1 USD = … FCFA) et sa source.
  - Le taux est enregistré sur la révision (`CaseRevision.exchange_rates`) et journalisé.
  - Il est repris dans le calcul et dans l'export PDF/Excel.
  - L'euro garde sa parité fixe ; aucun taux n'est deviné ni téléchargé.
- **Codes à subdivision unique** :
  - quand le tarif n'offre qu'une subdivision (8517.62 → 8517.62.00), elle est présélectionnée ;
  - « Confirmer les codes reconnus » la confirme en groupe, avec le motif de l'agent.
- **Acheteur** : « Bill to » imprimé entre le nom et l'adresse donnait l'adresse. C'est désormais le nom qui est lu.
- **Importateur** :
  - il est proposé (à confirmer) seulement si un client de la société porte exactement le nom de l'acheteur ;
  - sinon le manque cite l'acheteur lu, et aucune fiche n'est créée automatiquement.
- **Référentiel** : « Version active » affiche l'édition de consultation au lieu de « aucune ».
- **Récapitulatif du calcul** : en CIF/CIP, le fret et l'assurance sont « compris dans les prix » au lieu de « à confirmer ».

## Commandes et tests

- `cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest` : 344 réussis.
- `cd frontend && npm run typecheck && npm test && npm run build` : 76 réussis.
- Parcours navigateur (Playwright) sur une base locale, du dépôt de la facture à l'export.

## Limites

- Une édition « consultation » ne peut toujours pas être publiée « opérationnelle » : la règle exige un profil fiscal validé.
- Le calcul se fait quand même, mais il reste marqué « préparation ».
- Le taux de change est saisi par dossier. Il n'existe pas encore de table de cours partagée par la société.

## Prochaine étape

Table des cours de change de la société (date, source), proposée par défaut dans chaque dossier.
