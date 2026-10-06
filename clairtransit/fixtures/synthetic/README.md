# Jeux synthétiques

Toutes les données ici sont fictives. Aucun taux, code ou nom ne représente une donnée gabonaise réelle.

- **Jeu A** (lot 0) : deux sociétés et leurs utilisateurs. Créé par `python manage.py seed_demo`
  (`backend/apps/organizations/management/commands/seed_demo.py`) et, pour les tests, par `backend/tests/conftest.py`.
- Jeux G et H : à créer avec les lots 4 et 5 (voir `docs/specifications/03-plan-et-recette.md` §3).
- **Jeu F** (lot 1) : référentiel fictif. `referentiel-f.csv` (export CSV : doublon, code tronqué, code invalide,
  cellules vides, caractères de contrôle, colonne d'unités) et `referentiel-f.txt` (texte extrait de PDF : couverture,
  règles, section, chapitres et notes, position manquante, code sous une mauvaise position, doublon, code mal formé,
  point final). Utilisé par `backend/tests/test_tariffs.py`.
- **Jeux B à E** (lot 3) : factures fictives générées par `backend/apps/extraction/synthetic.py` (PDF texte, PDF
  multipage, PDF scanné, image nette ou dégradée, classeur Excel avec formules et lien externe). Elles sont produites à
  la volée par les tests et par `python manage.py build_synthetic_corpus <dossier>` (corpus d'évaluation avec les
  valeurs attendues). `referentiel-lot3.csv` : petit référentiel fictif dont les libellés correspondent à ces factures,
  pour les contrôles de code et les propositions de classement.
