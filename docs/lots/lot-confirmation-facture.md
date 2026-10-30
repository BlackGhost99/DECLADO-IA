# Confirmation des valeurs lues sur la facture : compte rendu

Date : 30 octobre 2026. Exigences : EXT-01, EXT-03, EXT-07, CLI-01, AUD-01. Test de recette : T72. Branche `confirmer-facture`.

Demande : « Même quand je confirme, rien ne semble pris en compte, je veux que ce soit simple. » Sur l'écran Documents, une valeur de facture « À vérifier » (fournisseur lu en tête de page, par exemple) ne pouvait pas être confirmée, et l'importateur « À rattacher » n'avait aucun bouton.

## Fonctionnalités terminées

- **Confirmer** : sur chaque valeur « À vérifier » de la facture, un clic garde la valeur lue et lève le signalement (`POST /api/v1/invoices/<id>/fields/<champ>/confirm`). La valeur passe « Confirmé ». Une relecture la garde, comme une saisie, et ne la remet pas « à vérifier ». Le journal enregistre `invoice.field_confirmed` avec le nom du champ seulement.
- **Corriger** ou **Saisir** : la valeur est remplacée (PATCH de la facture existant) ; elle devient « Saisi » et la correction est tracée.
- **Rattacher** l'importateur : choix d'une fiche de la société, ou création de la fiche au nom lu sur la facture ; le dossier est mis à jour (PATCH du dossier existant).
- **Détail des marchandises** : une ligne dont la marchandise a une décision en vigueur s'affiche « Confirmé », au lieu de garder le statut de la lecture.
- Textes en FR, EN, ES et AR.

## Tests exécutés

- Backend : ruff, makemigrations --check, pytest (316 passés, dont 4 dans `tests/test_confirmation_facture.py`).
- Frontend : typecheck, vitest (63 passés, dont 2 dans `tests/ConfirmationFacture.test.tsx`), build.

## Limites

- Les lignes de facture gardent leurs signalements « Absent du document » (référence fournisseur, origine) : ils se lèvent en saisissant la valeur dans « Données extraites ».
- Une valeur vide se saisit, elle ne se confirme pas (400).

## Prochaine étape

Circuit de validation interne du dossier (lot 5), puis TCI hors total (compte 2) et RI « calculée par SYDONIA ».
