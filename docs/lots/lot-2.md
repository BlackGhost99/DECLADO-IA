# Lot 2 — Dossiers et pièces : compte rendu de livraison

Date : 6 octobre 2026. Backlog couvert : DEV-010 à DEV-013. Démonstration de sortie : un dossier est créé, une ligne de facture est saisie avec son code, et ce code est contrôlé puis confirmé (captures livrées).

## Fonctionnalités réellement terminées

- **Dossiers** (DEV-010, DOS-01, CLI-02) :
  - Référence lisible unique par société et par année (`DOS-2026-0001`), via un compteur verrouillé.
  - Filtres par état, agent (« moi », « non affectés »), importateur, dates de création et texte. Filtrer par importateur liste ses anciens dossiers, sans rien réutiliser de leurs règles.
  - Importateur, édition et date facultatifs à la création : le brouillon reste enregistrable.
- **Révisions** :
  - La révision 1 est créée avec le dossier. Le mode vaut « démonstration » pour une société de démo, « simulation historique » sinon. Le mode opérationnel est impossible tant qu'aucune édition opérationnelle n'existe.
  - États prévus jusqu'à « validé en interne » et « archivé » ; seuls les états éditables acceptent des modifications (409 sinon).
  - Créer une révision après validation répond 409 tant que la validation (lot 5) n'existe pas.
- **Affectation** : un validateur ou un administrateur affecte à tout déclarant ou validateur actif de la société. Un déclarant peut prendre un dossier libre pour lui-même. Chaque affectation est journalisée.
- **Pièces** (DEV-011, DOC-01 à DOC-05) :
  - Stockage privé avec SHA-256, auteur, date, type détecté par le contenu et version (ADR-009).
  - Refus explicites, sans rien garder : format non accepté, contenu incohérent avec l'extension ou avec le type déclaré, fichier vide, taille au-delà de 50 Mo (413). Les limites sont affichées à l'écran.
  - PDF chiffré, PDF tronqué, image coupée et .xlsx chiffré ou cassé sont conservés et signalés, sans aperçu. Les autres pièces du dossier ne sont pas touchées.
  - Un fichier identique dans la société est signalé (409, avec les dossiers concernés) : l'utilisateur réutilise la pièce existante sans nouveau dépôt, ou garde les deux. Une autre société n'en apprend rien.
  - En-tête `Idempotency-Key` : un envoi répété renvoie le même rattachement.
  - Remplacement par une nouvelle version : l'original et son rattachement restent consultables.
  - Aperçu PDF et image dans la page, cellules A1 pour Excel (formules en texte, jamais recalculées). Téléchargement par lien temporaire lié à l'utilisateur.
- **Factures, lignes et marchandises** (DEV-012, DOS-03, EXT-04) :
  - Plusieurs factures par dossier, avec fournisseur, numéro, date, devise, incoterm, total imprimé et pièce.
  - Lignes saisies avec désignation, référence article, quantité, unité, prix, montant, origine, pièce et page sources. Elles sont marquées « Saisi ».
  - Le code douanier et l'intitulé de son champ (« HS Code ») sont saisis à part de la référence fournisseur. Un code envoyé comme nombre est refusé (400).
  - Une marchandise est préparée depuis une ou plusieurs lignes, avec les liens et les quantités/valeurs affectées.
- **Manques avant calcul et validation** (DOS-02, T04) :
  - Liste par niveau : dossier, révision, facture, ligne, marchandise.
  - Signale aussi, sans rien corriger : somme des lignes ≠ total imprimé (avec l'écart), quantité × prix ≠ montant, montant négatif (avoir), ligne non rattachée, pièce illisible, édition historique.
- **Contrôle et confirmation d'un code présent** (DEV-013, COD-01/02/03/05/07, ADR-010) :
  - États : retrouvé, incomplet avec subdivisions proposées (aucun zéro ajouté), introuvable avec le plus long préfixe existant, présent seulement dans une autre édition, ambigu (champ incertain ou codes contradictoires), absent (la référence fournisseur n'est jamais prise pour un code).
  - Constats : édition historique (bloquant pour un calcul opérationnel), date ou territoire hors édition, anomalies ouvertes de la source sur ce code, libellé abîmé, et absence de règles de cohérence encodées.
  - La décision (confirmer, compléter par une subdivision, remplacer avec une source) est motivée, attribuée et journalisée. Elle ne valide pas le dossier.
- **Concurrence et invalidation** (T33, WF-03) :
  - Chaque modification exige `row_version` ou `If-Match`. Une version périmée renvoie 409 sans rien écraser.
  - Une décision exige le dernier contrôle et la version courante de la marchandise.
  - Modifier le code, la désignation ou l'origine rend contrôle et décision « à revoir », sans les effacer.
- **Historique du dossier** (AUD-01/02) : `GET /cases/<id>/audit` liste les événements de ce seul dossier. Aucun texte de facture n'est recopié dans le journal.
- **Interface** : onglet Dossiers avec la liste filtrable, la création, le détail, les manques, les pièces (dépôt, doublon, aperçu, téléchargement), les factures et la saisie des lignes, les marchandises, le contrôle, la confirmation ou le complément, et l'historique.
- **Démonstration** : `seed_demo` crée le dossier fictif d'Alpha. Il contient une facture PDF synthétique, une ligne « HS Code 0101.10.00 » avec la référence article 12345678, et une marchandise prête à contrôler.

## Commandes

```bash
cd backend
python manage.py migrate
python manage.py seed_demo          # après la publication d'une édition, pour qu'elle soit présélectionnée
python manage.py runserver
cd ../frontend && npm run dev       # se connecter en declarant@alpha.demo, onglet Dossiers
```

Variables : `PRIVATE_STORAGE_ROOT`, `DOCUMENT_MAX_BYTES` (52428800) et `DOCUMENT_LINK_TTL_SECONDS` (300). Sous Docker, les pièces sont sur le volume `private`.

## Tests exécutés

| Commande | Résultat |
|---|---|
| `python -m pytest` (backend) | 114 réussis, dont 42 nouveaux (25 dossiers et codes, 17 pièces) |
| `ruff check .`, `ruff format --check .`, `makemigrations --check` | OK |
| `npm run typecheck`, `npm test`, `npm run build` | OK, 6 tests réussis |
| Parcours dans Chromium sur la base de développement (éditions réelles de consultation) | Déroulé : dossier ouvert, aperçu PDF servi (200, `inline`), code contrôlé puis confirmé. Un déclarant de Bêta obtient 404 sur le dossier d'Alpha. |

Correspondance avec la recette :
- T01 : dossiers, révisions, factures, lignes, marchandises, contrôles, décisions, historique, métadonnées, liens et octets des pièces sont tous en 404 pour l'autre société.
- T03 : référence unique, doublons d'importateur (lot 0), aucune règle réutilisée.
- T04 : brouillon multi-factures et multi-devises, manques par ligne.
- T05 : fichier valide, identique, trop grand, de faux type ou corrompu.
- T07 : référence de huit chiffres et HS Code restent deux champs.
- T11 : confirmation enregistrée, sans substitution.
- T12 : subdivisions, aucun zéro ajouté.
- T13 : original conservé, motif, aide à la recherche.
- T33 : 409 sur version périmée.
- T02/ACC-03 : une affiliation désactivée coupe aussi un lien déjà émis.

## Limites connues

- **Interface** : on peut ajouter des factures et des lignes et préparer les marchandises, mais leur modification n'existe pas encore à l'écran. L'API la permet (PATCH, testée) : c'est par elle que le passage « à revoir » est démontré.
- Le remplacement de pièce n'est disponible que par l'API (testé). Il n'est pas encore à l'écran.
- La capture de l'aperçu PDF est vide : le Chromium sans affichage ne dessine pas son lecteur PDF. La réponse servie a été vérifiée (200, `application/pdf`, `inline`, `SAMEORIGIN`), pas le rendu visuel.
- Pas d'adaptateur S3 : le stockage local privé est le seul branché (ADR-009). La limite de 500 pages par facture n'est pas appliquée, car elle demande la lecture du PDF (lot 3).
- Aucune règle de cohérence marchandise/code (état `inconsistent`) n'est encodée, ce que chaque contrôle signale. Les notes et exclusions restent à lire sur la fiche du code.
- Le code absent (`missing`) aboutit à une invitation à rechercher. Les propositions de classement (COD-06) arrivent au lot 3.
- Fractionnement et regroupement avancés (GRP-01/02) : une marchandise peut réunir plusieurs lignes, sans contrôle de compatibilité, ce qui relève du lot 4.
- Régime et territoire sont en saisie libre. Le Gabon est considéré comme couvert par une édition « CEMAC » : cette correspondance est à confirmer.

## Prochaine étape

Lot 3 : extraction assistée (PDF texte, XLSX, OCR à la demande) qui produit les mêmes observations localisées, avec correction sans perte de preuve. La reprise de DEV-007 dépend du PDF original du tarif.
