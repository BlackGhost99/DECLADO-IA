# Lot 3 bis — Numérisation des pièces d'un dossier : compte rendu de livraison

Date : 24 octobre 2026. Exigences : NUM-01 à NUM-08 (cahier des charges, « Numérisation des pièces »). Tests de recette : T39 à T45.

Demande : un dossier de transit peut compter plusieurs dizaines de feuilles papier ; l'agent doit pouvoir les numériser, au scanner ou au téléphone, sans les déposer une à une. La maquette a été validée avec le choix « Les deux » (scanner et téléphone ou webcam) et une consigne : le design de l'application ne change pas.

Démonstration, déroulée dans Chromium sur la base de développement avec un lot fictif scanné (6 pages, image seule, une page à l'envers) :
- Documents › « Numériser des pièces » ouvre « Ajouter les pièces du dossier » : Lot du scanner, Téléphone ou webcam, Fichiers déjà prêts, et les lots en cours.
- Le PDF déposé est découpé, lu par OCR et trié : Facture (p. 1 et 2, « titre « Facture » reconnu en haut de la page 1, n° FE-2026-0417 »), Document de transport (p. 4), Liste de colisage (p. 5 et 6) ; la page blanche est retirée.
- « Rattacher 3 pièces au dossier » crée trois pièces PDF dans le dossier, avec leur provenance, et lance la lecture de la facture.

## Fonctionnalités terminées

- **Lot du scanner** (NUM-01) :
  - un ou plusieurs fichiers PDF, PNG, JPEG ou TIFF, découpés en pages dans l'ordre du dépôt ;
  - originaux conservés comme documents de la société (empreinte, auteur) ;
  - 300 pages au plus par lot (`SCAN_BATCH_MAX_PAGES`), refus explicite 413 `BATCH_TOO_LARGE` ;
  - le TIFF n'est accepté que dans un lot ; déposé directement comme pièce, il est refusé avec un message qui oriente vers le lot.
- **Découpage proposé** (NUM-02) :
  - titre reconnu dans le haut de la page (facture, connaissement ou B/L, liste de colisage, certificat d'origine, attestation d'assurance), avec son numéro quand il est lu ;
  - mention « Page k/n » ; page blanche qui ferme la pièce en cours et est retirée ;
  - une page sans titre suit la pièce en cours ; deux numéros différents ne sont jamais fusionnés ;
  - chaque pièce dit sa raison ; une page sans indice reste « non classée ».
- **Prise de vue** (NUM-03) :
  - téléphone (appareil photo du navigateur) ou webcam ;
  - type de pièce choisi avant la première photo, « Pièce terminée » pour passer à la suivante ;
  - photo recadrée sur la feuille quand elle se détache du fond.
- **Lecture** (NUM-04, NUM-07) :
  - couche texte du PDF quand elle existe, sinon Tesseract sur le serveur ;
  - page remise à l'endroit : avis de Tesseract (OSD) quand il est net, sinon les deux sens sont lus et le plus sûr est gardé ;
  - page peu lisible (peu de mots ou confiance basse) signalée « à reprendre » ;
  - sans OCR installé, les pages sont signalées et rien n'est déduit.
- **Tri par l'agent** (NUM-05) : couper la pièce à une page, joindre à la précédente, déplacer vers une pièce, une nouvelle pièce ou les pages non classées, pivoter, retirer, remettre, changer le type, reprendre une page (la nouvelle prend la même place). Le découpage automatique ne refait jamais un choix de l'agent.
- **Rattachement** (NUM-06) :
  - sur action explicite ; une pièce PDF par pièce, nommée « DOS-… Facture.pdf » (numérotée si le type se répète) ;
  - lecture OCR des factures lancée ; les pages non classées restent dans le lot ;
  - lot rattaché figé ; lot vide refusé (409 `NOTHING_TO_ATTACH`).
- **Sécurité et traçabilité** (NUM-08) :
  - modèles rattachés à la société, lus via `for_organization` ; accès croisé testé sur chaque point d'accès (404) ;
  - écriture réservée aux déclarants et validateurs ; révision non modifiable refusée ;
  - chaque geste passe par `apps/scans/services.py` et est journalisé (`scan.*`), visible dans l'historique du dossier ;
  - aucun service externe : la lecture tourne sur le serveur, l'application reste utilisable sans internet.
- **Écrans** (même design que le reste de l'application : cartes, boutons, puces et couleurs existants) :
  - bouton « Numériser des pièces » sous « Ajouter un document » ; les autres écrans sont inchangés ;
  - « Ajouter les pièces du dossier », « Trier le lot », « Prise de vue », « Pièces du dossier ».

## Points d'accès

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/v1/cases/<id>/scan-batches` | lots du dossier ; créer un lot (`scanner` ou `camera`) |
| GET | `/api/v1/scan-batches/<id>` | lot, pièces et pages |
| POST | `/api/v1/scan-batches/<id>/files` | déposer des fichiers (champ `files`, multiple) |
| POST | `/api/v1/scan-batches/<id>/photos` | ajouter une photo (`file`, et `piece_id` ou `usage`) |
| POST | `/api/v1/scan-batches/<id>/finish`, `/attach`, `/cancel` | fin de prise de vue, rattachement, abandon |
| PATCH | `/api/v1/scan-pages/<id>` | rotation, retrait, pièce |
| POST | `/api/v1/scan-pages/<id>/split`, `/replace` | couper, reprendre |
| GET | `/api/v1/scan-pages/<id>/image[?size=thumb]` | image de la page |
| PATCH, POST | `/api/v1/scan-pieces/<id>`, `/join-previous` | type, joindre |

## Commandes

```bash
cd backend
python manage.py migrate                     # nouvelle application apps.scans
celery -A config worker -B -l info           # lit les pages des lots en arrière-plan
```

Nouvelle variable (`.env.example`) : `SCAN_BATCH_MAX_PAGES` (300 par défaut). Tesseract (fra, eng) est déjà dans l'image Docker et la CI ; les postes des agents n'installent rien.

## Tests exécutés

- `cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest` : 167 réussis, dont 17 dans `tests/test_scans.py` (T39 à T44).
- `cd frontend && npm run typecheck && npm test && npm run build` : 25 réussis, dont 5 dans `tests/Scans.test.tsx` (T45).

## Limites

- Pas de code QR ni de lien temporaire pour le téléphone : l'agent ouvre ClairTransit sur le téléphone avec l'adresse du serveur de l'agence et se connecte. Depuis « localhost », l'écran le rappelle.
- La reconnaissance des titres couvre les intitulés courants en français et en anglais ; un autre intitulé laisse la page « non classée » ou dans la pièce en cours.
- Recadrage simple (feuille claire sur fond sombre), sans redressement de perspective.
- En développement sans Celery, la lecture se fait pendant la requête : un gros lot est lent à déposer.
- Les pièces rattachées sont des PDF d'images ; seules les factures sont mises en lecture automatiquement.

## Prochaine étape

Essai avec de vraies pièces scannées d'une agence (échantillon autorisé) pour mesurer la séparation et la lisibilité, puis fusion de la refonte de l'interface (PR #5) et de ce lot.
