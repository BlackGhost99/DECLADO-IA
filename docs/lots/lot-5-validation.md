# Lot 5 (première partie) : circuit de validation interne

Date : 30 octobre 2026. Exigences : WF-01, WF-02, WF-03, AUD-01. Tests de recette : T73 à T75. Tâche : DEV-025. Branche `validation-interne`.

Demande : le bouton « Valider le dossier » était grisé. Décision de l'utilisateur (30/10/2026) : un agent peut valider un dossier qu'il a lui-même soumis, s'il a le rôle validateur ou administrateur.

## Fonctionnalités terminées

- **Soumettre** (`POST /api/v1/cases/<id>/workflow/submit`) : possible depuis Brouillon, En préparation ou À corriger. Refusé (409) tant qu'un point bloquant reste, avec leur liste. En mode opérationnel, le calcul doit aussi être complet. Le dossier passe « À valider » et n'est plus modifiable.
- **Retourner pour correction** (`.../workflow/return`) : validateur ou administrateur, motif obligatoire. Le dossier passe « À corriger » et redevient modifiable.
- **Valider** (`.../workflow/validate`) : validateur ou administrateur, commentaire facultatif. Refusé (409) si le calcul a changé depuis la soumission (taux modifié, barème activé). Le dossier passe « Validé en interne ».
- **Calcul figé** : le calcul validé est enregistré dans la décision. L'onglet Calculs l'affiche ensuite, avec la date, même si un taux change.
- **Décisions** : ajout seul (`RevisionDecision`), avec acteur, motif, empreinte et instantané ; chaque transition est journalisée (`revision.submitted`, `revision.returned`, `revision.validated`).
- **Écrans** : boutons Soumettre, Valider et Demander une correction, liste des décisions, prérequis à jour, textes en FR/EN/ES/AR. « Validé » reste une validation interne, jamais une acceptation par la Douane.

## Tests exécutés

- Backend : ruff, makemigrations --check, pytest (315 passés, dont 3 dans `tests/test_validation.py`).
- Frontend : typecheck, vitest (64 passés, dont 3 dans `tests/Validation.test.tsx`), build.

## Limites

- Nouvelle révision après validation (WF-04) et exports PDF/XLSX (EXP-01 à EXP-03) : faits dans le lot suivant, voir `lot-6-exports-revisions.md`.
- Les points bloquants viennent du contrôle de complétude existant : importateur, date prévue, régime, champs de facture et de ligne (origine comprise), codes confirmés.

## Prochaine étape

Faite : TCI au compte 2 et RI par SYDONIA (#44), puis `lot-6-exports-revisions.md`.
