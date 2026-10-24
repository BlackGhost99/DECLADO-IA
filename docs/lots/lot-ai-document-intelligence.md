# Bloc 4 — Intelligence documentaire et graphe des expéditions

Statut : relations documentaires déterministes V1 et validation humaine ; aucune IA externe opérationnelle.

## Fonctions livrées
- Reconnaissance conservatrice des références dans les dernières observations d'extraction.
- Relations plusieurs-à-plusieurs pièce/facture, expédition/pièce et expédition/facture.
- Expéditions reconstituées seulement quand la même référence explicite de transport apparaît dans au moins deux pièces.
- Refus des liens automatiques vers un numéro de facture qui correspond à plusieurs factures métier.
- Détection d'une référence de facture lue différente de la valeur courante ; aucune modification des factures.
- Approbation, rejet et résolution motivée, journalisés par société et par utilisateur.
- Création manuelle d'une expédition et association de documents partagés.
- Interface FR/EN/ES/AR dans le dossier, sans chatbot.

## API
- GET/POST /api/v1/revisions/{revision_id}/document-intelligence
- POST /api/v1/revisions/{revision_id}/document-invoice-links
- POST /api/v1/revisions/{revision_id}/shipments
- POST /api/v1/revisions/{revision_id}/shipments/{shipment_id}/links
- POST /api/v1/document-intelligence/links/{model}/{id}/review
- POST /api/v1/document-intelligence/shipments/{id}/confirm
- POST /api/v1/document-intelligence/conflicts/{id}/resolve

Les écritures exigent le rôle déclarant ou validateur, la société active et une révision modifiable.
Un rejet ou une confirmation existants ne sont jamais renversés par une relance automatique.

## Parcours test
1. Importer et extraire les pièces lisibles d'un dossier.
2. Ouvrir « Intelligence documentaire » et cliquer « Analyser les références ».
3. Examiner les références du B/L, les factures et les documents partagés proposés.
4. Confirmer/rejeter les associations puis confirmer l'expédition.
5. Ajouter manuellement les liens non prouvables par les seules observations.
6. Résoudre chaque contradiction avec un motif, sans changement silencieux de la facture.

## Limites explicites
Le fournisseur IA externe reste désactivé (AI_PROVIDER=disabled) et ne doit pas être présenté comme actif.
Aucune reconnaissance sémantique ou analyse du texte intégral des pièces non extraites n'est garantie.
La précision sur documents réels, l'OCR de transport spécialisé, la protection ClamAV déployée,
et le choix d'un fournisseur de modèle conforme à la confidentialité sont à valider séparément.
Les droits et taxes continuent de dépendre exclusivement des moteurs réglementaires déterministes.

Un jeu de tests synthétiques couvre 80 documents, 10 factures, les pièces partagées,
l'idempotence, les contradictions et l'isolation des sociétés.
