# Lot « Fin de vie du dossier » (WF-05, WF-06, T97 à T99)

Demande du 2 novembre 2026 : poursuivre les modules restants en attendant les textes d'exonération. Jusqu'ici, un dossier validé n'avait pas de suite.

## Fonctionnalités terminées

- **Marquer comme déposé en douane** (déclarant, validateur ou administrateur), seulement après la validation interne. L'agent saisit le n° de la déclaration SYDONIA (texte) et la date de dépôt (jamais dans le futur). Le dépôt s'enregistre une seule fois par révision, comme une décision journalisée.
- ClairTransit ne consulte pas SYDONIA. L'écran le dit : ce n° ne vaut pas acceptation par la Douane.
- **Archiver** (validateur ou administrateur) :
  - le dossier passe en lecture seule et la date d'archivage est enregistrée ;
  - le calcul figé à la validation reste celui qui fait foi ;
  - aucune nouvelle révision n'est possible ;
  - un dossier non validé (abandonné) s'archive avec un motif obligatoire ;
  - un dossier « À valider » doit d'abord être décidé.
- **Sortir des archives** : administrateur de la société seulement, avec un motif. Le dossier revient à l'état qu'il avait avant l'archivage.
- Le n° de déclaration apparaît sur le dossier et dans la liste des dossiers.
- Textes en FR, EN, ES et AR.

## Limites

- Le n° SYDONIA n'est pas vérifié, et son format n'est pas imposé : il dépend du bureau et doit encore être confirmé.
- Le dépôt d'une révision n'est pas modifiable. En cas d'erreur, il faut créer une nouvelle révision (motif) puis valider de nouveau.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `tests/test_fin_de_vie.py` : T97, T98, T99.
- `frontend/tests/Lifecycle.test.tsx` : saisie du dépôt, puis affichage d'un dossier archivé et sortie des archives par l'administrateur.

## Prochaine étape

Encart « Exonérations appliquées » et n° de dépôt dans les exports.
