# Lot : dépôt groupé, pièces de plusieurs envois réparties en dossiers

## Fonctionnalités terminées

- Nouvel écran **Dépôt groupé** (menu principal) : l'agent dépose en une fois les pièces de plusieurs envois.
- Chaque pièce passe par l'antivirus, puis est lue comme dans un dossier : type d'après le titre, partie (acheteur, destinataire du B/L, assuré) et références imprimées.
- **Proposer les dossiers** : regroupement sur les références partagées uniquement (n° de facture porté ou cité, n° de B/L porté ou cité, n° de conteneur). Chaque dossier proposé affiche ses raisons (« Facture IIC-2026-7784 · 3 pièces »).
- Le nom de l'importateur ne regroupe jamais seul (une société peut avoir plusieurs envois). Deux noms différents dans un groupe sont signalés « à vérifier ». Une pièce sans référence lue reste « À classer ».
- L'agent peut renommer un dossier, déplacer une pièce vers un autre dossier, un nouveau dossier ou « À classer ».
- **Créer les dossiers** : un dossier par groupe, pièces jointes avec leur type, lecture complète demandée ; la préparation automatique habituelle suit (facture, marchandises, importateur proposé s'il existe déjà).
- Un fichier déjà présent dans la société n'est pas doublé : la pièce existante est reprise et l'écran indique les dossiers où elle figure.
- Textes en FR, EN, ES, AR.

## API

- `POST /api/v1/intake/documents` (multipart `file`) : pièce contrôlée, conservée sans dossier, lue.
- `POST /api/v1/intake/proposal` `{document_ids}` : dossiers proposés et pièces à classer.
- `POST /api/v1/intake/cases` `{groups: [{title, document_ids}]}` : création des dossiers confirmés.

## Tests

- T83 (`backend/tests/test_depot_groupe.py`) sur les 9 pièces fictives fournies (`fixtures/synthetic/depot-groupe/`).
- Vérifié dans le navigateur : 9 pièces déposées, 3 dossiers proposés (BatiPro, EquaTech, Textilia) avec facture, B/L et conteneur en raison, 3 dossiers créés, pièces lues, factures et marchandises préparées.

## Limites

- Le regroupement s'appuie sur la lecture des factures, titres de transport et assurances. Une pièce d'un autre type (colisage, certificat d'origine) ou une image sans OCR reste « À classer ».
- Pas de lecture par IA en ligne dans ce lot : tout repose sur les références imprimées.

## Prochaine étape

- Lire aussi la liste de colisage et le certificat d'origine pour les rattacher par n° de facture.
