# Lot : projet de déclaration au modèle DAU, tableau des calculs, logo

## Fonctionnalités terminées

- **Projet de déclaration (modèle DAU)** : nouvel export `dau` (onglet Export, bouton « Générer le projet de déclaration »). PDF d'une page reprenant la disposition des cases 1 à 50 du Document Administratif Unique, version **importation**.
  - Cases remplies depuis le dossier : modèle, régime, exportateur (fournisseurs), destinataire (importateur), déclarant, pays d'origine, de provenance et de destination, incoterm et lieu, devise et total facture, nombre d'articles, fret, assurance et autres frais (ou « compris » selon l'incoterm), valeur CIF, conteneurs, titres de transport, articles (désignation, code SH, origine, quantité, valeur, régime), pièces jointes et impositions de préparation (assiette, taux, montant, total).
  - Une case sans donnée prouvée reste vide (masses, colis, n° d'opérateur…). Les cases de la Douane (n° de déclaration, enregistrement, 47 à 50) restent vides.
  - Case 33 et pied de page : « projet préparé avec ClairTransit, à saisir dans SYDONIA : ce document ne vaut pas déclaration et n'est pas accepté par la Douane ». Aucune mention de conformité SYDONIA.
  - TCI marquée « (c. 2) » ; RI laissée à SYDONIA (non calculée).
  - Brouillon marqué « BROUILLON » ; logo de l'application en filigrane.
  - Journalisé comme les autres exports (`revision.exported`), isolé par société.
- **Calculs, détail par marchandise** : colonnes numériques alignées à droite (en-têtes compris), filets verticaux, ligne de totaux quand il y a plusieurs articles (un total inconnu reste « ? », jamais zéro).
- **Logo temporaire** sur l'écran de connexion. La barre latérale ne change pas.

## Tests

- T82 (`backend/tests/test_exports.py::test_t82_dau_project_is_prefilled_from_the_case_and_never_claims_acceptance`).
- Backend 345 tests, frontend 76 tests, build OK. Vérifié dans le navigateur sur un dossier fictif validé (EquaTech, USD, B/L, conteneur) : une page, colonnes alignées.

## Limites

- Disposition inspirée du formulaire fourni (version export) ; ce n'est pas un formulaire officiel et il ne remplace pas la saisie SYDONIA.
- Masses, colis, marques et n° d'opérateur ne sont pas encore extraits : cases vides.
- Au-delà d'une dizaine d'articles, le document passe sur plusieurs pages.

## Prochaine étape

- Lire masses et colis sur le B/L et la packing list pour remplir les cases 23 à 26, 35, 39 et 40.
