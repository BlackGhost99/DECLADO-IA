# Lecture des pièces selon leur type : compte rendu de livraison

Date : 28 octobre 2026. Exigences : LEC-01 à LEC-10 (cahier des charges, « Extraction et contrôle documentaire »). Tests de recette : T51 à T57. Branche `lecture-pieces`, partie de `mise-en-route`.

Demande : « la détection ne se passe pas comme prévu ». La société demandait une facture commerciale, une facture d'assurance et un titre de transport. Les trois pièces ont été déposées une à une, sans numérisation. Résultat constaté :
- facture commerciale : fournisseur, importateur et total « non trouvés », date ambiguë, aucune marchandise ;
- B/L : « la lecture automatique concerne les factures » ;
- facture d'assurance : lue comme une facture, une fausse ligne de marchandise.

Causes :
- le rôle choisi au dépôt (« Facture », « Document de transport »…) ne connaissait ni l'assurance ni le fret, et le nouveau dossier devinait « Facture » dès que le nom contenait « facture » ;
- seules les factures étaient lues ;
- la lecture ne trouvait pas les valeurs rangées en grille, à côté ou sous leur libellé ;
- le fournisseur imprimé en tête, sans libellé, était ignoré ;
- « Ocean freight » n'était pas reconnu comme un frais, et un total partageant sa cellule avec son libellé n'était pas lu ;
- le contrôle documentaire ne connaissait que le rôle choisi, pas le type de la pièce.

Les trois pièces fictives « BatiPro » de `fixtures/synthetic/batipro/` reproduisent ces mises en page. Elles servent de jeu d'essai.

## Fonctionnalités terminées

- **Type reconnu d'après le titre** (LEC-07) :
  - au dépôt, le titre de la première page d'un PDF texte donne le type : « COMMERCIAL INVOICE », « BILL OF LADING », « FACTURE D'ASSURANCE » (même sur deux lignes), etc. ; à défaut, le nom du fichier sert d'indice faible ;
  - le menu du dépôt propose d'abord « Reconnaître d'après le titre (recommandé) », puis les pièces demandées par la société, puis les autres types ;
  - un type reconnu reste une proposition : l'écran montre le titre lu et un bouton « Confirmer ce type », qui enregistre une classification signée avec le titre lu pour motif ;
  - un type choisi au dépôt vaut confirmation par l'agent qui dépose ; un type inconnu est refusé avant tout stockage ;
  - si le titre contredit le rôle choisi par l'agent (assurance déposée comme facture), l'écart est montré avec « Utiliser ce type » ; rien n'est changé sans lui ;
  - les pièces déjà déposées sont reconnues à leur prochaine lecture.
- **Lecture propre au type** (LEC-08, LEC-09) :
  - titre de transport : n°, date, chargeur, destinataire, partie à notifier, navire, voyage, ports, lieu de livraison, facture citée, conteneur, colis, poids, volume, conditions de fret ;
  - assurance : émetteur, n°, date, devise, police, assuré, titre de transport et facture cités, navire, conteneur, valeur assurée, prime totale ;
  - facture de fret : émetteur, n°, date, devise, références citées, navire, ports, montant ;
  - chaque valeur est sourcée (page et zone, « Voir la source »), chaque absence est « non trouvée » ;
  - ces pièces ne créent ni facture ni marchandise.
- **Facture mieux lue** (LEC-01 à LEC-06) :
  - valeurs rangées en grille, à côté ou sous leur libellé, avec le libellé noté en provenance ;
  - fournisseur lu en tête (raison sociale avec forme juridique S.L., SARL, SA, Ltd, GmbH…), marqué déduit et « à vérifier » ;
  - acheteur ou destinataire lu sur la facture : affiché « À rattacher » quand le dossier n'a pas d'importateur, signalé s'il diffère de l'importateur du dossier ; jamais rattaché d'office ;
  - « Ocean freight », « Sea freight », « Frais de port » lus comme frais ; « Port de déchargement » reste un lieu ;
  - total lu même quand le libellé et le montant partagent une cellule ou sont hors tableau ;
  - date 03/10/2026 lue jour/mois seulement si l'adresse de l'émetteur indique un pays où c'est l'usage (ici « Espana »), marquée déduite avec la raison ; sinon elle reste ambiguë.
- **Contrôle documentaire et rapprochement** (LEC-10) :
  - une pièce de type reconnu coche la pièce demandée « Reçu, à vérifier · type reconnu, à confirmer » ; elle n'est jamais vérifiée sans confirmation ;
  - le choix de classement est prérempli avec le type reconnu et le titre lu ;
  - le n° de B/L, la facture citée et la police lus sur le B/L et l'assurance alimentent l'analyse des références ; les liens restent proposés, jamais acceptés d'office.
- **Nouveau dossier** : chaque pièce déposée est reconnue d'après son titre et lue si son type a une lecture, et non plus seulement la première facture.
- **Langues** : tous les nouveaux textes en français, anglais, espagnol et arabe (`frontend/src/i18n/lecture.ts`).

Aucune IA n'intervient : la reconnaissance et la lecture sont déterministes, à partir du texte du PDF.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

Migrations : `cases/0006_lecture_des_pieces` (type reconnu, acheteur, usages Assurance et Facture de fret) et `scans/0002_usages_assurance_fret`.

## Tests exécutés

- **Backend** : 266 tests réussis, dont 14 dans `tests/test_lecture_pieces.py` (T51 à T57).
- **Frontend** : 44 tests réussis, dont 4 dans `tests/Lecture.test.tsx` (choix de la lecture, menu du dépôt, écart de type et confirmation motivée, informations lues).
- **Dans l'application** (Chromium, société de démonstration avec les trois pièces demandées) : nouveau dossier avec les trois pièces BatiPro, chacune reconnue (« Facture commerciale », « Connaissement maritime (B/L) », « Facture d'assurance ») et lue à sa façon ; facture : fournisseur, acheteur à rattacher, n°, date jour/mois à vérifier, devise, total 18 554,00, 3 marchandises ; contrôle documentaire : trois pièces « reçues, à vérifier ».

## Limites

- Les pièces fictives imitent les captures reçues ; les vraies pièces de l'utilisateur peuvent avoir d'autres mises en page. Une pièce mal lue doit être envoyée pour ajuster les libellés connus.
- Les PDF produits par un navigateur sont lus, mais le nombre de colis et le chiffre de contrôle du conteneur peuvent manquer.
- Scans et photos : le type ne se reconnaît d'après le titre qu'après lecture OCR ; au dépôt, seul le nom du fichier sert d'indice.
- Un dossier existant garde la fausse facture créée par l'ancienne lecture d'une assurance : déposer à nouveau les pièces dans un nouveau dossier.
- Les informations lues sur un B/L ou une assurance ne remplissent pas encore les champs du dossier (fret, assurance pour la valeur en douane) : elles sont affichées et sourcées, à reporter par l'agent.

## Prochaine étape

Reporter le fret et l'assurance lus sur les pièces dans la valorisation, comme propositions à confirmer, et comparer les références croisées (n° de facture cité sur le B/L, valeur assurée et total de la facture).
