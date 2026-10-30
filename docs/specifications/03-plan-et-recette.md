# ClairTransit — Plan de développement et recette

Version 1.0 — 6 octobre 2026.

## 1. Stratégie de livraison

Développer un parcours utilisable à chaque lot. Démarrer avec données synthétiques et consultation historique. Les dépendances externes non disponibles sont représentées par des interfaces explicites, avec saisie manuelle lorsque pertinente. Un substitut de développement doit être identifiable et ne doit pas être livré comme une fonction réellement raccordée.

Les estimations de durée seront établies après le lot 0 et un échantillon documentaire. L’ordre ci-dessous décrit les dépendances, pas un engagement calendaire.

| Lot | Contenu | Dépendances | Démonstration de sortie |
|---|---|---|---|
| 0 — Socle | Dépôt, environnements, Django/React/PostgreSQL, comptes, sociétés, CI | Choix de versions compatibles | Deux sociétés connectées, données isolées, application démarrable par la documentation |
| 1 — Référentiel | Import brut, anomalies, notes, hiérarchie, recherche, administration | Lot 0 et sources accessibles | Rechercher un code, lire son contexte, ouvrir la preuve, consulter une anomalie |
| 2 — Dossiers et pièces | Importateurs, dossiers, uploads privés, lignes manuelles, historique | Lot 0 ; lot 1 pour codes | Créer un dossier et contrôler un code présent sur une ligne saisie |
| 3 — Extraction assistée | PDF/Excel/OCR, observations localisées, correction, codes présents, recherche de remplacement | Lots 1–2 et corpus d’essai | Charger une facture et corriger une extraction sans perte de preuve |
| 4 — Valorisation et calcul | Change, frais/répartition, règles, exemptions, résultats détaillés | Lots 1–3 ; profils synthétiques puis métier | Calcul reproductible, taux manquant bloquant, absence de double fret |
| 5 — Validation et export | Soumission, approbation, révisions, PDF/XLSX, tests de bout en bout | Lots 0–4 | Dossier approuvé, exporté puis révisé sans modifier l’historique |
| 6 — Pilote métier | Cas réels anonymisés, validation du profil fiscal, performance, sauvegardes/restauration | Lots 0–5 et référents métier | Accord de recette sur un périmètre explicite et guide d’exploitation |

## 2. Backlog prêt à distribuer

### Lot 0

DEV-001 Initialiser dépôt et versions verrouillées ; commande de démarrage documentée.
DEV-002 Créer utilisateurs, sociétés et affiliations ; sessions, CSRF et rôles.
DEV-003 Établir les services bornés à la société et les tests d’accès croisés.
DEV-004 Mettre en place migrations, journal d’événements et CI.

Terminé si : les commandes documentées permettent de démarrer depuis un dépôt propre, les migrations passent, les comptes de test ont les bons droits et les tests d’isolation passent. Aucun secret réel dans les fixtures.

### Lot 1

DEV-005 Créer sources, imports bruts, éditions, nœuds, notes et anomalies.
DEV-006 Importer l’Excel en conservant valeurs/formules/caches ; rapport de comptage et anomalies.
DEV-007 Extraire le PDF par coordonnées et contexte ; vue de contrôle, couverture par page/chapitre.
DEV-008 Ajouter recherche exacte/préfixe/texte, navigation parents et source.
DEV-009 Ajouter publication historique et contrôle d’applicabilité ; résoudre les corrections sans supprimer la source.

Terminé si : chaque donnée affichée renvoie à sa source, les doublons suspects restent visibles, « autres » a son contexte, le code garde ses zéros et une source historique n’est pas activée comme tarif actuel. Aucun objectif artificiel de nombre de lignes PDF basé sur le seul compteur regex de l’audit.

### Lot 2

DEV-010 Créer importateurs, dossiers, révisions et affectations.
DEV-011 Ajouter stockage privé, prévisualisation et accès contrôlé aux pièces.
DEV-012 Créer lignes facturées/marchandises et formulaire de saisie manuelle.
DEV-013 Ajouter observation et confirmation d’un code existant, concurrence de modifications.

Terminé si : un utilisateur prépare manuellement un dossier complet de test, la preuve du code est conservée et un utilisateur d’une autre société ne peut accéder ni au dossier ni aux octets du document.

### Lot 3

DEV-014 Implémenter adaptateurs PDF texte et XLSX ; tâches et suivi.
DEV-015 Implémenter OCR à la demande et cas d’échec récupérables.
DEV-016 Structurer factures/lignes, valeurs et zones sources ; comparer totaux.
DEV-017 Distinguer code fournisseur/douanier/ambigu ; détecter absent/incomplet/incohérent.
DEV-018 Ajouter recherche et propositions justifiées, corrections et relances non destructrices.
DEV-019 Évaluer l’IA sur corpus et raccorder le fournisseur retenu seulement après configuration des données et secrets.

Terminé si : la facture avec code correct suit le chemin court de confirmation ; une référence fournisseur n’est pas transformée en code douanier ; une relance préserve les corrections ; la saisie manuelle fonctionne si le fournisseur IA échoue. L’IA peut rester désactivée pour les premiers essais si elle n’est pas nécessaire au parcours démontré.

### Lot 4

DEV-020 Modéliser devises, change et composantes de valorisation.
DEV-021 Répartir les frais avec conservation des totaux et preuve de leur inclusion/exclusion.
DEV-022 Implémenter langage de règles borné, validation de graphe et résolution datée.
DEV-023 Produire calculs figés, résultats partiels explicites et gestion des exemptions.
DEV-024 Tester profils fictifs puis exemples métier avec leurs sources ; garder les modes séparés.

Terminé si : résultats déterministes, taxes inconnues visibles, total absent si incomplet, versions/arrondis enregistrés et changement de données invalidant le calcul. La validation métier des taux est une condition du mode opérationnel, pas du moteur synthétique.

### Lot 5

DEV-025 Implémenter transitions et vérification atomique des données à approuver.
DEV-026 Générer PDF/XLSX avec mode, source, version, code textuel et détail des taxes.
DEV-027 Créer une révision après approbation ; conserver l’export précédent.
DEV-028 Tester le parcours complet et écrire les guides utilisateur/administrateur.

Terminé si : un dossier ne peut être approuvé sur un ancien calcul, les permissions sont appliquées côté serveur et les exports identifient sans ambiguïté brouillon, simulation ou validation interne.

### Lot 6

DEV-029 Constituer corpus anonymisé et décisions de référence avec un transitaire.
DEV-030 Confirmer profils applicables, modalités d’arrondi et critères de regroupement.
DEV-031 Mesurer qualité extraction/recherche et temps du parcours ; corriger les défauts bloquants.
DEV-032 Tester restauration et charge ; finaliser hébergement, conservation et exploitation.

Terminé si : le rapport de recette indique périmètre couvert, cas réussis/échoués, limites connues et responsables de validation. L’intégration officielle est un chantier séparé tant que ses formats ne sont pas établis.

## 3. Jeux de données de recette

A. Deux sociétés A et B, utilisateurs déclarant/validateur/admin, dossiers différents.
B. Facture synthétique simple avec HS identifié, référence article distincte, prix et quantités.
C. Facture avec code absent, autre avec code à six chiffres et autre avec référence numérique ambiguë.
D. Facture multipage avec en-têtes répétés, sous-totaux, remise, frais et plusieurs devises sur des factures distinctes.
E. PDF scanné lisible, scan dégradé, PDF protégé, fichier corrompu, XLSX avec formule externe.
F. Référentiel synthétique avec parents, « autres », notes, code invalide, doublon et dates divergentes.
G. Profil fiscal fictif TEST_ONLY ; règles à taux zéro, inconnues, exemptions et dépendances cycliques.
H. Copies de consultation des références historiques fournies ; aucune modification des originaux.
I. Corpus client anonymisé, à obtenir : les cas synthétiques ne prouvent pas la qualité sur documents réels.

Aucune fixture ne doit présenter un taux synthétique comme un taux gabonais réel. Les différences de taux observées entre sources servent à tester le conflit, pas à décider automatiquement quelle source est correcte.

## 4. Matrice de recette

| Test | Exigences couvertes | Scénario / résultat attendu |
|---|---|---|
| T01 | ACC-01, ACC-02, DOC-04, AUD-02 | A tente listes/détails/téléchargements/jobs de B : aucun accès ni fuite de métadonnées |
| T02 | ACC-03 | Désactiver un utilisateur : accès révoqué, décisions passées toujours attribuées |
| T03 | CLI-01, CLI-02, DOS-01 | Créer/rechercher importateur et dossier ; doublon signalé, référence unique, anciennes règles non appliquées implicitement |
| T04 | DOS-02, DOS-03 | Brouillon avec plusieurs factures/devises/origines : sauvegarde possible, manques affichés par ligne |
| T05 | DOC-01, DOC-02, DOC-03, DOC-05 | Fichier valide, identique, trop grand, faux type ou corrompu : original conservé ou refus explicite sans casser le dossier |
| T06 | EXT-01, EXT-02, EXT-03 | Extraire facture synthétique : champs et lignes attendus, chaque valeur reliée à sa zone/cellule |
| T07 | EXT-04, COD-01 | Champ « Référence » de huit chiffres et « HS Code » : deux observations distinctes ; aucune assimilation automatique |
| T08 | EXT-05 | Description tronquée et quantité illisible : valeurs inconnues et revue demandée ; aucun nombre inventé |
| T09 | EXT-06, EXT-08 | Facture multipage avec sous-totaux/frais/remise : pas de double comptage, écart expliqué |
| T10 | EXT-07 | Corriger puis relancer extraction : correction conservée, contradiction présentée à l’utilisateur |
| T11 | COD-02, COD-03, COD-07 | Code douanier présent reconnu : confirmation enregistrée, aucune substitution silencieuse, applicabilité contrôlée |
| T12 | COD-04 | Code incomplet : sous-positions pertinentes et question ; aucun ajout automatique de zéros |
| T13 | COD-05 | Code introuvable/ancien/incohérent : original conservé et motif, aide à la recherche |
| T14 | COD-06, REC-01 | Code absent : propositions issues du référentiel avec preuves, ou questions si insuffisant |
| T15 | REC-02, REC-03 | Recherche « autres »/synonyme : chemin affiché, historique contextualisé, bonne édition |
| T16 | VAL-01, VAL-03 | Prix comportant fret documenté : transport non ajouté deux fois ; change sourcé et direction vérifiée |
| T17 | VAL-02 | Charge 100,00 / trois parts égales, profil de test : somme 100,00, reliquat stable et tracé |
| T18 | VAL-04 | Méthode non automatisée : saisie justifiée acceptée selon rôle, pas de valeur calculée inventée |
| T19 | GRP-01, GRP-02 | Diviser/regrouper : provenance et totaux conservés ; origines ou traitements incompatibles refusés |
| T20 | TAX-01, TAX-07 | Date sans profil validé : mode opérationnel bloqué ; simulation historique identifiée |
| T21 | TAX-02, TAX-05 | Profil TEST_ONLY : 100000, A10 %, B18 % sur valeur+A → 10000, 19800, total29800 avec détails |
| T22 | TAX-03, TAX-06 | Taux absent ≠ taux0 : taxe inconnue/totalnull ; avec zéro connu résultat explicite nul |
| T23 | TAX-04 | Exemption conditionnelle sans preuve : attente ; preuve validée : application et justification conservées |
| T24 | TAX-01, TAX-02 | Deux règles applicables en conflit ou graphe cyclique : refus expliqué, aucun choix arbitraire |
| T25 | WF-01, WF-02 | Soumission incomplète refusée ; retour motivé ; approbation réservée au rôle autorisé |
| T26 | WF-03 | Modification après calcul ou pendant job : ancien calcul non courant, approbation refusée tant que recalcul requis |
| T27 | WF-04, AUD-01 | Révision d’un dossier approuvé : ancienne version inchangée, auteurs et motifs consultables |
| T28 | EXP-01, EXP-03 | Export brouillon/historique/validé : marquage exact, version et détail ; aucune mention d’acceptation douanière |
| T29 | EXP-02 | XLSX : code 01011010 conserve son zéro ; contenu commençant par = reste du texte sûr |
| T30 | REF-01, REF-02 | Import Excel/PDF : empreinte, édition, formules et caches conservés ; liens externes non exécutés |
| T31 | REF-03, REF-05 | Code répété et taux litigieux : anomalie, preuve avant/après, correction validée séparée du brut |
| T32 | REF-04, REF-06 | Publication/retrait : version immuable, historique consultable, aucune activation actuelle du PDF2009 implicite |
| T33 | ACC-01, WF-03 | Deux utilisateurs modifient même révision : 409 pour version périmée, aucune perte silencieuse |
| T34 | EXT-07, AUD-01 | Worker relancé deux fois : pas de lignes/export/decision dupliqués ; tentative et résultat traçables |
| T35 | COD-06, TAX-02 | Document contenant des instructions hostiles : aucune instruction exécutée, aucun taux/code extérieur inventé |
| T36 | DOC-02, WF-04 | Restauration : retrouver dossier, pièces, décision, calcul et export avec leurs empreintes |
| T37 | REC-01, DOS-01 | Mesurer p95 recherche et ouverture dans l’environnement/corpus définis ; rapport avec charge et résultats |
| T38 | DOC-04, EXT-03 | Parcours clavier, erreurs lisibles et navigation vers preuve ; audit d’accessibilité des écrans principaux |
| T39 | NUM-01, NUM-02, NUM-04 | Lot de 6 pages (facture de 2 pages, page blanche, connaissement, colisage, annexe) : 3 pièces proposées avec leur raison, page blanche retirée, originaux conservés, rien rattaché ; plusieurs fichiers et TIFF dans l’ordre ; TIFF refusé hors lot ; limite de pages explicite |
| T40 | NUM-05 | Couper, joindre, déplacer vers une nouvelle pièce, déclasser, pivoter, retirer, changer le type, reprendre une page : chaque geste journalisé et jamais refait par le découpage |
| T41 | NUM-06, NUM-08 | Rattachement : une pièce PDF par pièce, nommée et typée, factures mises en lecture ; pages non classées laissées dans le lot ; lot vide refusé ; lot rattaché figé ; révision validée refusée |
| T42 | NUM-03 | Photos prises pièce par pièce : pièces et types choisis à la prise de vue, photo recadrée sur la feuille |
| T43 | NUM-04, NUM-07 | Scan sans couche texte lu par OCR, page à l’envers remise à l’endroit ; sans OCR, pages signalées sans titre ni type inventé |
| T44 | NUM-08 | Société B sans accès aux lots, pages, images et pièces de A (404) ; administrateur sans rôle de préparation en lecture seule (403 en écriture) |
| T45 | NUM-01 à NUM-06 | Écrans : trois façons d’ajouter les pièces, lots en cours, tri avec raisons et page à reprendre, gestes envoyés au serveur, pièces rattachées avec provenance |
| T46 | ACC-04 | Serveur vide : écran de mise en service, compte exploitant créé une seule fois (second essai refusé, 409), double authentification exigée côté serveur ; aucune société ni donnée fictive sans l’option démo |
| T47 | ACC-05 | Demande publique : seul le profil ouvert et les pays CEMAC acceptés ; acceptation crée la société et l’invitation de l’administrateur ; refus motivé ; chaque décision journalisée |
| T48 | ACC-06, ACC-02 | Console : administrateur de société et anonyme refusés (403) ; l’exploitant ne lit aucun dossier ni importateur ; société suspendue : plus aucun accès à ses données, réactivation possible |
| T49 | ACC-07 | Lien d’activation : expiré, utilisé, annulé ou société suspendue refusé ; compte existant rattaché avec son propre mot de passe ; renouvellement invalide l’ancien lien |
| T50 | ACC-08, ACC-02 | Agences et invitations d’une société invisibles d’une autre (404) ; agence d’une autre société refusée ; limite de sièges respectée ; écrans en quatre langues, RTL en arabe |
| T51 | LEC-01 à LEC-05 | Facture fictive BatiPro (PDF généré et PDF de navigateur) : fournisseur lu en tête, acheteur, n°, devise, total 18 554,00 EUR, 3 marchandises, fret maritime en frais |
| T52 | LEC-04, LEC-06 | Date 03/10/2026 sans pays d’émetteur : ambiguë, jamais devinée ; « Ocean freight » frais, « Port de déchargement » non |
| T53 | LEC-07 | Titres « COMMERCIAL INVOICE », « BILL OF LADING », « FACTURE D’ASSURANCE » (sur deux lignes) donnent le type |
| T54 | LEC-08, LEC-09 | B/L et facture d’assurance : informations lues avec leur source, absences « non trouvées » |
| T55 | LEC-07 à LEC-09 | Dépôt « reconnaître d’après le titre » des 3 pièces : chaque pièce lue à sa façon, une seule facture créée, prime 111,93 sourcée |
| T56 | LEC-10 | Pièces demandées par la société « reçues, à vérifier », non confirmées ; B/L cité par la facture et l’assurance proposé au rapprochement |
| T57 | LEC-07 | Type choisi au dépôt confirmé ; type inconnu refusé (422) sans fichier stocké ; colisage sans lecture ; assurance déposée comme facture : écart montré, lecture d’assurance après confirmation ; écrans en quatre langues |
| T58 | IAL-01, IAL-02 | Sans fournisseur, puis avec une clé mais sans activation par la société : B/L fictif lu, aucun appel, rien de journalisé |
| T59 | IAL-03, IAL-04 | Mode automatique, B/L fictif à trois libellés inconnus : seules les informations non trouvées sont demandées, avec le texte lu et ses repères de page ; propositions « à vérifier » sourcées |
| T60 | IAL-05, IAL-06 | Extrait inventé, valeur hors de l’extrait, champ non demandé : écartés ; fournisseur injoignable : lecture aboutie, échec journalisé |
| T61 | IAL-07, IAL-08 | Client qui refuse : rien n’est envoyé et l’écran le dit ; seul l’administrateur lève le refus ; plafond atteint : rien ne part |
| T62 | IAL-09, IAL-03 | Sur demande : « Compléter avec l’IA » ; proposition acceptée, valeur saisie, pas de seconde demande sur la même lecture ; facture remplie seulement après acceptation |
| T63 | IAL-10, IAL-08 | Réglage réservé à l’administrateur ; activation refusée sans clé ; clé jamais renvoyée ; coût inconnu pour un modèle sans prix ; écrans en quatre langues, RTL en arabe |
| T64 | ACC-02, IAL-10 | Autre société : ni pièce, ni proposition, ni journal (404) ; journal des envois non modifiable |
| T65 | IAL-05, IAL-06 | Consigne : le texte de la pièce est une donnée, jamais une instruction ; schéma strict ; fournisseur inconnu ou clé absente : aucun repli |
| T66 | IAL-08 | Plafond compté depuis le premier jour du mois |
| T67 | IAL-04, IAL-06 | Adaptateurs Claude et Gemini, avec leur vraie bibliothèque, contre un serveur local factice : texte et schéma envoyés, erreurs 401, 429 et refus traduites ; aucun appel réel |
| T68 | TAX-01, TAX-03 | Classeur « Tarif CEMAC SWD » fictif : chaque taux gardé avec sa cellule, sous-positions nationales, écarts avec la feuille TEC et taxes vides signalés ; édition du référentiel créée avec la vraie ligne de la feuille comme preuve ; un nouvel import active le nouveau barème et garde l'ancien |
| T69 | TAX-01, TAX-04 | Modification d'un taux : refusée à une société (403) ; motif, date d'effet et référence obligatoires ; ajout seul, journalisé ; l'ancien taux reste appliqué avant la date d'effet ; la dernière modification l'emporte ; redevance informatique saisie pour tous les codes |
| T70 | TAX-02, TAX-05, TAX-06, TAX-07 | Calcul d'un dossier : base 549 070 et DDI 10 % d'une déclaration réelle retrouvés au franc (54 907, 108 716, 5 491, 2 197, 275, 6 040, 1 099) ; code non confirmé, devise sans taux ou redevance non saisie : taxe inconnue, total absent, somme connue affichée ; FOB sans pièce de fret ni d'assurance : provisoire ; mode du dossier rendu |
| T71 | ACC-02 | Calcul d'un dossier d'une autre société : 404 ; sans connexion : refusé |

Tests T01, T11, T20–T29, T31–T35 bloquants avant mise en service du périmètre correspondant. Les autres tests P0 restent obligatoires ; les exigences P1 peuvent être reportées explicitement dans une livraison réduite.

## 5. Validation métier à organiser

Le référent transitaire fournit ou valide un ensemble de dossiers anonymisés avec pièces, codes retenus, bases, taxes, exonérations et résultat final. Chaque résultat attendu doit être rattaché à une période et à une source. Les désaccords sont consignés ; ils ne sont pas résolus par le modèle d’IA.

Échantillon initial proposé : au moins 20 dossiers représentatifs, comprenant plusieurs factures, gros volumes, codes présents/absents, exonérations et documents dégradés. Ce nombre est une cible de travail, pas une garantie statistique de qualité. Le corpus doit couvrir les familles réellement traitées par les premiers clients.

Mesurer séparément : détection des lignes, exactitude des montants, code fourni correctement lu, proposition de classement et calcul. Un bon score global ne doit pas masquer une erreur sur les codes ou taxes.

## 6. Définition de terminé pour une livraison

- Exigences annoncées livrées et reliées aux tests.
- Migrations applicables ; application démarrable selon le guide.
- Tests pertinents exécutés et résultats enregistrés, y compris permissions.
- Aucun secret ni document client non autorisé dans le dépôt.
- Limites et fonctions simulées indiquées clairement.
- Documentation des décisions et des points ouverts mise à jour.
- Démonstration du parcours utilisateur, pas seulement des endpoints.
- Pour les calculs opérationnels : profil validé, preuves et cas métier concordants.

## 7. Points ouverts et responsables proposés

| Question | Responsable de réponse | Échéance fonctionnelle |
|---|---|---|
| Nature et présence des codes sur factures | Porteur du projet + transitaire | Calibration du lot 3 |
| Origine des colonnes spécifiques Excel | Détenteur du classeur + référent douanier | Publication des règles concernées |
| Tarif/fiscalité Gabon applicables et dates | Référent douanier | Calcul opérationnel lot 6 |
| Arrondis et regroupements | Référent métier | Recette lots 4–6 |
| Séparation préparateur/validateur | Société pilote | Paramétrage lot 5 |
| Formats du système officiel | Société pilote / éditeur concerné | Chantier d’intégration ultérieur |
| Hébergement, conservation et fournisseur IA | Porteur du projet | Traitement de pièces réelles / production |
| Volumes et budget | Porteur du projet + équipe de développement | Dimensionnement après lot 0 |
