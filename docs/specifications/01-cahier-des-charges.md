# ClairTransit — Cahier des charges fonctionnel

Version 1.0 — 6 octobre 2026 — Document de travail pour développement et validation métier.

## 1. Objet et résultat attendu

ClairTransit accompagne les sociétés de transit dans la préparation des dossiers de dédouanement de leurs clients importateurs, avec un premier périmètre Gabon/CEMAC. Il rassemble les pièces, extrait les marchandises et les codes douaniers déjà présents, contrôle les données, aide à résoudre les anomalies et prépare un calcul détaillé ainsi qu’un dossier exportable.

L’utilisateur principal est le déclarant ou agent de transit. L’importateur fournit les pièces ; la Douane reste un acteur externe. Un dossier validé dans ClairTransit signifie « validé en interne par la société de transit », pas « accepté par la Douane ».

Le développement doit aboutir à une application web utilisable par plusieurs sociétés, avec données isolées, documents consultables, corrections traçables et calculs reproductibles. Le nom de travail est ClairTransit ; Customs AI décrit la composante d’assistance.

## 2. Éléments établis, hypothèses et questions ouvertes

### Établi dans les échanges et l’audit

- Les sociétés de transit reçoivent les documents des importateurs et préparent les dossiers.
- Un dossier peut comporter plusieurs factures et de nombreuses marchandises.
- Deux références historiques ont été étudiées : un PDF CEMAC de 551 pages, édition 2009/SH 2007, et un Excel intitulé 2016 comprenant 5 609 codes.
- L’Excel comporte des valeurs manquantes, libellés abrégés et formules liées à un fichier absent. Le PDF apporte les règles et notes mais présente des ambiguïtés d’extraction et certaines incohérences.
- Le parcours doit donner la priorité aux codes présents dans les factures : extraction, contrôle et conservation.

### Hypothèses de conception proposées, modifiables sans changer le principe métier

| ID | Hypothèse pour la V1 | Conséquence |
|---|---|---|
| H01 | Application web utilisée surtout sur ordinateur | Interface de travail avec document et tableau côte à côte |
| H02 | Interface française ; documents français/anglais | Conserver le texte original et proposer une description normalisée |
| H03 | Plusieurs sociétés utilisatrices à terme | Isolation des données dès la première version |
| H04 | Validation par un second utilisateur pour les dossiers opérationnels | Politique configurable par société ; mode démonstration explicite |
| H05 | Export préparatoire PDF et XLSX en première version | Intégration officielle traitée après obtention des spécifications |
| H06 | Connexion disponible, parfois instable | Sauvegarde progressive et reprise ; travail entièrement hors ligne hors V1 |

### Informations à confirmer pendant le projet

La présence réelle et la nature des codes sur les factures n’ont pas encore été vérifiées sur un échantillon. Certains champs peuvent être des références fournisseur plutôt que des codes HS. Le système doit reconnaître cette incertitude.

Restent à confirmer : documents habituels, pays/version des codes fournis, règles de regroupement, droits de chaque rôle, volumes, modalités d’hébergement et de conservation, référentiel et fiscalité en vigueur, méthodes d’arrondi, formats du logiciel douanier cible et calculs réels validés.

Ces points ne bloquent pas la création des dossiers, l’import historique, la recherche ou la correction des extractions. Ils conditionnent la mise en service des fonctions qui en dépendent.

## 3. Objectifs et indicateurs

Objectifs : réduire la ressaisie, accélérer le traitement de dossiers volumineux, retrouver les règles pertinentes, rendre les anomalies visibles et permettre à un responsable de comprendre chaque décision.

Mesurer sur un échantillon client : temps actif par dossier, taux de champs corrigés après extraction, proportion de codes déjà présents et correctement repris, nombre d’anomalies non résolues, taux d’accord des propositions avec une validation métier, délai de validation et écarts de calcul. Comparer à une mesure initiale avant de promettre un gain chiffré.

Les scores d’extraction et de recherche restent des indicateurs techniques ; ils ne sont pas présentés comme une garantie juridique.

## 4. Périmètre et priorités

P0 = obligatoire pour le lot concerné ; P1 = utile après le parcours principal ; P2 = évolution.

### V1

Comptes et sociétés ; importateurs ; dossiers et pièces ; extraction PDF/image/XLSX ; correction de lignes ; extraction et contrôle des codes ; recherche assistée en cas de besoin ; référentiel versionné ; valorisation et calcul paramétrés ; validation interne ; exports préparatoires ; journal des actions.

### Évolutions P2

Portail importateur, intégration avec le système douanier officiel, paiement de droits, comptabilité, signature électronique avancée, travail hors ligne complet, autres pays, recherche sémantique et automatisation étendue des notes juridiques. Aucun de ces éléments n’est implicitement inclus dans la V1.

## 5. Acteurs et permissions

| Action | Déclarant | Validateur | Administrateur de société | Gestionnaire du référentiel |
|---|---|---|---|---|
| Consulter dossiers de sa société | Selon affectation/politique | Oui | Oui | Non par défaut |
| Créer dossier, joindre pièces, corriger | Oui | Oui si autorisé | Selon rôle métier attribué | Non |
| Proposer/retenir un code avant validation | Oui | Oui | Selon rôle métier | Non |
| Soumettre à validation | Oui | Oui | Selon rôle métier | Non |
| Valider/rejeter un dossier | Non | Oui | Seulement avec rôle validateur | Non |
| Gérer utilisateurs de sa société | Non | Non | Oui | Non |
| Importer/revoir/publier un référentiel | Non | Non | Non | Selon permissions distinctes |
| Modifier une règle fiscale publiée | Non | Non | Non | Créer une nouvelle version |

Les rôles peuvent être cumulés. Une société peut imposer qu’un utilisateur ne valide pas sa propre préparation. L’administrateur technique n’obtient pas automatiquement l’accès métier à toutes les pièces. Les accès de support éventuels sont temporaires et journalisés.

## 6. Parcours nominal

1. Connexion et sélection de la société lorsque plusieurs affiliations existent.
2. Création du dossier : référence interne, importateur, agent, territoire, date de déclaration envisagée, régime et origine si connus.
3. Ajout des factures et pièces ; typage manuel possible.
4. Extraction en arrière-plan ; affichage de l’avancement, des erreurs et des documents nécessitant une intervention.
5. Vérification des informations et des lignes dans une vue document/tableau.
6. Pour chaque ligne, reprise du code douanier présent puis contrôle. En cas d’absence, ambiguïté, incomplet ou incohérence, ouverture de l’aide au classement.
7. Complément de la valorisation : devise, change, fret, assurance, ajustements, quantités et justificatifs.
8. Calcul détaillé, résolution des éléments bloquants, soumission.
9. Vérification par le responsable, retour pour correction ou validation interne.
10. Génération du dossier préparatoire et archivage de sa version.

Un échec d’OCR ou d’IA doit laisser possible la saisie manuelle. Un changement après validation crée une révision ; il ne réécrit pas le dossier déjà approuvé.

## 7. Exigences fonctionnelles détaillées

### Comptes, sociétés et importateurs

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| ACC-01 | P0 | Authentifier l’utilisateur et appliquer ses droits côté serveur sur chaque action |
| ACC-02 | P0 | Refuser tout accès à une donnée d’une autre société, y compris par URL de document ou tâche en arrière-plan |
| ACC-03 | P0 | Désactiver un compte sans effacer ses décisions historiques ; invalider ses accès actifs |
| ACC-04 | P0 | Installation neuve sans aucune donnée : le premier écran crée une seule fois le compte de l’exploitant ClairTransit, double authentification obligatoire ; données de démonstration seulement sur demande explicite et marquées fictives |
| ACC-05 | P0 | Ouvrir une société de deux façons : créée par l’exploitant depuis sa console, ou demandée publiquement puis acceptée par lui ; aucune demande ne crée de compte avant acceptation ; refus motivé ; décision journalisée |
| ACC-06 | P0 | Console de l’exploitant : sociétés, état, sièges, suspension et réactivation ; aucun accès aux dossiers, pièces ou importateurs des sociétés |
| ACC-07 | P0 | Invitation par lien à usage unique, valable 72 heures et renouvelable : l’invité choisit lui-même son mot de passe, puis active la double authentification (obligatoire pour un administrateur) ; aucun mot de passe n’est choisi pour quelqu’un d’autre |
| ACC-08 | P0 | Administration de la société : agences, invitations avec rôles et agence, désactivation et réactivation, limite de sièges ; premiers pas guidés pour l’administrateur |
| CLI-01 | P0 | Créer un importateur avec nom, coordonnées, identifiants déclarés et contacts ; signaler les doublons possibles |
| CLI-02 | P1 | Rechercher les anciens dossiers d’un importateur sans réutiliser automatiquement leurs règles fiscales |

### Dossiers et pièces

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| DOS-01 | P0 | Générer une référence unique par société ; filtrer les dossiers par état, agent, importateur et date |
| DOS-02 | P0 | Autoriser un dossier incomplet en brouillon ; rendre visibles les champs nécessaires avant calcul/validation |
| DOS-03 | P0 | Conserver plusieurs factures, fournisseurs, devises et origines dans un dossier |
| DOC-01 | P0 | Accepter PDF, PNG, JPEG, XLSX ; formats et limites affichés ; refuser un contenu incohérent avec le type déclaré |
| DOC-02 | P0 | Conserver original, nom, empreinte, date d’ajout, auteur et type ; remplacement par nouvelle version |
| DOC-03 | P0 | Identifier un fichier identique déjà ajouté dans la même société ; laisser décider de sa réutilisation |
| DOC-04 | P0 | Prévisualiser PDF/images ; afficher feuille/cellule pour Excel ; téléchargement soumis aux droits |
| DOC-05 | P0 | Signaler fichier protégé, corrompu, non lisible ou dépassant la limite ; préserver les autres pièces du dossier |

### Numérisation des pièces

Un dossier peut compter plusieurs dizaines de feuilles papier. L’agent les numérise en une fois ; l’application sépare les pièces et lui montre le résultat avant tout rattachement.

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| NUM-01 | P0 | Déposer un lot du scanner : un ou plusieurs fichiers PDF, PNG, JPEG ou TIFF, découpés en pages dans l’ordre du dépôt ; originaux conservés ; nombre de pages par lot limité et affiché |
| NUM-02 | P0 | Proposer un découpage en pièces : titre reconnu en haut de page (facture, connaissement, colisage, certificat d’origine, assurance), mention « page k/n », page blanche ; chaque proposition dit sa raison ; une page sans indice reste « non classée », jamais devinée |
| NUM-03 | P0 | Prendre les pages en photo (téléphone ou webcam) ; la pièce et son type sont choisis à la prise de vue ; la photo est recadrée sur la feuille |
| NUM-04 | P0 | Lire chaque page : couche texte du PDF, sinon OCR sur le serveur ; page remise à l’endroit ; page peu lisible signalée |
| NUM-05 | P0 | Laisser l’agent corriger : couper, joindre, déplacer, pivoter, retirer, remettre, changer le type, reprendre une page à la même place ; le découpage proposé ne refait jamais un choix de l’agent |
| NUM-06 | P0 | Rattacher sur action explicite : une pièce PDF par pièce, nommée d’après le dossier et le type, avec sa provenance (lot et numéros de page) ; lecture des factures lancée ; les pages non classées restent dans le lot |
| NUM-07 | P0 | Ne rien inventer : sans OCR ou sur page illisible, aucun titre, type ou valeur n’est déduit ; la page est signalée pour reprise ou saisie |
| NUM-08 | P0 | Isolation par société, droits de préparation (lecture seule sinon), révision non modifiable refusée, journal de chaque geste ; fonctionne sans internet (OCR sur le serveur de l’agence) |

Limites initiales proposées : 50 Mo par fichier, 500 pages par facture PDF et 1 000 lignes par dossier de référence. L’import administratif du référentiel accepte au moins le PDF de 551 pages. Ces limites sont configurables et à réviser après mesure.

### Extraction et contrôle documentaire

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| EXT-01 | P0 | Extraire fournisseur, numéro/date de facture, devise, totaux et lignes sans écraser les corrections humaines |
| EXT-02 | P0 | Extraire référence article, description, quantité, unité, prix unitaire, montant, code présent et origine si indiquée |
| EXT-03 | P0 | Attacher chaque valeur extraite à une page/zone ou feuille/cellule ; distinguer lu, inféré et saisi |
| EXT-04 | P0 | Conserver le libellé du champ contenant le code ; référence fournisseur et code douanier dans deux champs distincts |
| EXT-05 | P0 | Afficher les informations absentes et ambiguës ; ne pas inventer quantité, code, taux ou montant |
| EXT-06 | P0 | Vérifier somme des lignes, remises, frais et total selon les informations présentes ; afficher l’écart et les composantes |
| EXT-07 | P0 | Relancer l’extraction comme nouvelle tentative comparée à l’ancienne, sans perte des corrections |
| EXT-08 | P1 | Distinguer en-têtes répétés, sous-totaux, lignes de frais et marchandises dans les factures multipages |

Une ligne au même libellé/prix qu’une autre peut être légitime. Le logiciel signale une duplication présumée ; il ne supprime aucune marchandise automatiquement. Les avoirs ou retours sont signalés et traités explicitement, sans les assimiler à des lignes positives ordinaires.

### Codes tarifaires et recherche

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| COD-01 | P0 | Conserver le code tel que lu, son champ source, le code normalisé et sa provenance |
| COD-02 | P0 | Vérifier existence, édition, territoire, date et niveau déclarable ; code reconnu ne signifie pas classement juridiquement validé |
| COD-03 | P0 | Pour un code présent cohérent : le reprendre et demander la confirmation métier, sans générer inutilement une liste de remplacements |
| COD-04 | P0 | Pour un code incomplet : afficher ses subdivisions pertinentes et les caractéristiques qui les distinguent |
| COD-05 | P0 | Pour un code inconnu/ambigu/incohérent : expliquer l’anomalie, conserver l’original et proposer une recherche |
| COD-06 | P0 | Pour un code absent : rechercher à partir de la description et des caractéristiques, avec notes et exclusions |
| COD-07 | P0 | Enregistrer auteur, justification et source lors d’une confirmation ou modification |
| REC-01 | P0 | Rechercher code exact, préfixe et texte ; afficher édition, chemin complet, notes, source et statut des données |
| REC-02 | P0 | Afficher « autres » avec ses parents et respecter les lignes intermédiaires de nomenclature |
| REC-03 | P1 | Ajouter synonymes contrôlés et historique de décisions propres à la société, avec leur contexte et leur date |

Le code peut avoir six chiffres SH et demander une subdivision ; sa longueur attendue dépend du référentiel cible. Le logiciel ne complète pas automatiquement par des zéros. Un code étranger ou ancien exige une correspondance documentée. Si la facture contient seulement une référence article, le code douanier reste absent.

### Valorisation, regroupement et calcul

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| VAL-01 | P0 | Conserver prix, devise, conditions de vente, frais inclus/exclus, change, justificatif et date |
| VAL-02 | P0 | Répartir les frais avec une méthode choisie et documentée ; conserver la somme exacte après arrondi |
| VAL-03 | P0 | Signaler un fret/assurance déjà inclus ; demander confirmation des composantes pour éviter le double comptage |
| VAL-04 | P0 | Permettre une valeur en douane saisie et justifiée lorsque la méthode ne peut pas être automatisée en V1 |
| GRP-01 | P0 | Préserver toutes les lignes originales ; tout fractionnement/regroupement conserve ses liens et répartitions |
| GRP-02 | P0 | Exiger compatibilité du code, origine, régime, traitement fiscal et unités pertinentes avant regroupement déclaratif |
| TAX-01 | P0 | Résoudre un profil fiscal validé pour territoire, date, régime et origine ; afficher la version |
| TAX-02 | P0 | Calculer avec décimales et règles d’assiette/arrondi explicites, indépendamment du modèle d’IA |
| TAX-03 | P0 | Distinguer connu, inconnu, exonéré, non applicable et conflit ; une cellule vide ne vaut jamais zéro |
| TAX-04 | P0 | Exiger justificatif et champ d’application pour une exonération conditionnelle |
| TAX-05 | P0 | Afficher chaque taxe, base, taux/unité, montant, règle et source ; conserver les montants intermédiaires |
| TAX-06 | P0 | Si une règle obligatoire manque, afficher les résultats partiels identifiés et aucun total complet trompeur |
| TAX-07 | P0 | Distinguer simulation historique, essai fictif et calcul opérationnel dans l’écran et l’export |

Les règles en vigueur, assiettes, arrondis et conversions fiscales seront validés avec un professionnel et des exemples réels. Les taux historiques observés ne sont pas activés automatiquement pour les dossiers actuels.

### Validation, exports et historique

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| WF-01 | P0 | Soumission uniquement lorsque les contrôles obligatoires passent ; liste explicite des blocages |
| WF-02 | P0 | Le responsable peut valider ou retourner pour correction avec un motif |
| WF-03 | P0 | Modifier une donnée pertinente invalide le calcul concerné et impose nouvelle validation |
| WF-04 | P0 | Une révision après validation crée une nouvelle version ; anciennes décisions et exports restent consultables |
| EXP-01 | P0 | Export PDF préparatoire : identification, marchandises/codes, valorisation, taxes, sources, état et validations |
| EXP-02 | P0 | Export XLSX avec codes textuels, montants, unités et onglet de métadonnées ; neutraliser les cellules pouvant devenir des formules |
| EXP-03 | P0 | Un brouillon exporté porte un marquage visible ; seul un dossier approuvé porte la validation interne |
| AUD-01 | P0 | Journaliser corrections, changements de code, décisions, règles utilisées et génération d’exports |
| AUD-02 | P0 | Filtrer l’historique par acteur/date/type sans exposer les données d’une autre société |

Le prix du service du transitaire, les débours et la facturation commerciale sont à distinguer des droits/taxes douaniers ; leur module commercial n’est pas inclus dans le calcul fiscal V1.

### Administration du référentiel

| ID | Priorité | Exigence et résultat vérifiable |
|---|---|---|
| REF-01 | P0 | Importer une source avec empreinte, provenance, édition annoncée et période vérifiée ou inconnue |
| REF-02 | P0 | Conserver données brutes, formules Excel et valeurs en cache sans exécuter les liens externes |
| REF-03 | P0 | Signaler doublons, codes mal formés, taux manquants, parents inconnus et divergences entre sources |
| REF-04 | P0 | Distinguer consultation historique et publication pour usage opérationnel |
| REF-05 | P0 | Toute correction possède ancienne valeur, nouvelle valeur, justification et pièce probante |
| REF-06 | P0 | Publier une version immuable ; nouvelle modification = nouvelle version ; retrait n’efface pas l’historique |

## 8. Écrans et comportements attendus

### Accueil

Liste des dossiers récents, tâches assignées et dossiers en attente de correction/validation. Filtres par état, importateur et agent. Indicateurs utiles : pièces à traiter, lignes à vérifier, calcul incomplet. Aucun montant fiscal présenté sans son état.

### Dossier

En-tête : référence, importateur, agent, état et version. Onglets : Pièces, Marchandises, Valeur et taxes, Validation, Historique. Sauvegarde explicite et indication « enregistré » ; avertissement en cas de conflit de modification.

### Contrôle des marchandises

Document à gauche, tableau à droite, ouverture de la zone source au clic. Colonnes : description, référence fournisseur, code lu, code retenu, quantité/unité, montant/devise, origine, état du contrôle. Détail d’une ligne : caractéristiques, preuve, notes et décisions. Les corrections de masse affichent un aperçu des lignes et des champs concernés avant application.

### Contrôle d’un code

Code présent : montrer résultat de vérification et action « Confirmer ». Code incomplet : montrer subdivisions et questions. Code absent : ouvrir recherche. Code incohérent : montrer original, raison et alternatives. Tout changement affiche clairement avant/après et demande une justification.

### Valeur et taxes

Composantes de valeur, devise/change, frais inclus et répartitions ; détail des taxes par ligne et synthèse. Un panneau liste les informations manquantes avec liens vers les champs. La saisie d’un taux de simulation ne modifie pas le référentiel.

### Validation

Synthèse, anomalies résolues et restantes, modifications depuis dernière revue, règles et calculs figés. Actions soumettre, retourner, approuver selon rôle. Un message d’erreur indique l’action possible, par exemple « Origine absente pour la ligne 12 : complétez-la pour déterminer le régime applicable ».

## 9. États et blocages

Dossier : brouillon → préparation → à valider → validé → archivé. Retour : à valider → à corriger → préparation. Révision d’un validé : nouvelle révision en préparation. Archivage ne signifie pas acceptation douanière.

Traitement documentaire distinct : en attente, en cours, terminé, terminé avec anomalies, échec, annulé. La fin d’une extraction ne valide aucune ligne.

Une anomalie possède sévérité et portée : informative, à vérifier, bloquante ; document, ligne, calcul ou dossier. Seuls les blocages pertinents interdisent l’action concernée. On peut sauvegarder et rechercher dans un dossier dont le calcul est bloqué.

Avant validation opérationnelle : données obligatoires complètes, codes confirmés, aucun conflit obligatoire, valorisation justifiée, profil applicable validé, calcul à jour complet, preuves nécessaires présentes et permissions respectées.

## 10. Exigences non fonctionnelles et exploitation

- Isolation : tests d’accès entre sociétés sur API, documents, recherche, tâches et exports.
- Traçabilité : toute décision critique attribuée, datée et rattachée aux versions ; pas d’effacement ordinaire du journal.
- Confidentialité : accès privés aux pièces, transport chiffré, secrets hors du dépôt, journaux techniques sans contenu de factures par défaut.
- Résilience : tâches reprenables, tentatives limitées, saisie manuelle disponible, pas de duplications après relance.
- Accessibilité : navigation clavier, contrastes lisibles, erreurs non signalées par la couleur seule ; cible WCAG 2.2 AA pour les parcours principaux, à vérifier.
- Ergonomie : français simple, montants/devises explicites, dates non ambiguës, sauvegarde perceptible.
- Maintenabilité : modules, migrations, documentation de démarrage, tests métier, versions de dépendances verrouillées.
- Sauvegardes : base et stockage documentaire, restauration testée ; objectifs initiaux proposés RPO 24 h, RTO 4 h, à confirmer avec l’hébergement.
- Conservation : durée et procédure d’effacement à définir contractuellement avant production ; données de développement synthétiques/anonymisées.

Cibles de performance proposées, non garanties avant mesure : recherche p95 ≤ 1 seconde pour 50 000 nœuds et 20 utilisateurs actifs ; ouverture d’une première page de 50 lignes p95 ≤ 2 secondes sur 1 000 lignes ; accusé de réception d’un traitement ≤ 2 secondes après transfert complet du fichier. Mesurer sur un environnement de référence documenté, hors latence réseau pour l’API. Le temps d’OCR/IA dépend des pièces et doit être mesuré sur un corpus représentatif avant engagement.

## 11. Livrables et recette

Livrables : code applicatif, migrations, importateurs de sources, configuration de développement et production, jeux synthétiques, tests automatisés, manuel utilisateur court, guide d’administration du référentiel et procédure de restauration. Les spécifications techniques et la matrice de recette jointes détaillent leur réalisation.

La recette technique valide le logiciel. La recette métier valide les règles et exemples de dossiers. La mise en service du calcul opérationnel exige les deux. Un démonstrateur avec données historiques peut être livré avant cela, avec son mode visible et ses actions limitées.

Aucune échéance ferme ni budget n’est fixé dans ce document. Le chiffrage suivra le premier lot, l’échantillon de factures et les contraintes d’hébergement.
