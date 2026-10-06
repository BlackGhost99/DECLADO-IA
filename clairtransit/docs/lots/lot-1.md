# Lot 1 — Référentiel : compte rendu de livraison

Date : 6 octobre 2026. Backlog couvert : DEV-005, DEV-006 et DEV-008 en entier ; DEV-007 et DEV-009 en partie (voir les limites).
Mise à jour le même jour après réception du classeur Excel d'origine.

## Sources reçues et traitement

| Source fournie | Nature réelle | Traitement |
|---|---|---|
| `2016_TARIF_DOUANE_EXCEL.xlsx` | **classeur original** (1 feuille, 5 609 lignes, 10 073 formules) | importé avec formules et caches : **source de référence** pour cette édition |
| `2016_TARIF_DOUANE_EXCEL.csv` | export CSV du même classeur | importable en tant que copie dérivée ; mêmes codes, n'apporte rien de plus que le .xlsx |
| `tarif-des-douanes-de-la-cemac-…pdf.txt` | texte déjà extrait du PDF, sans coordonnées | importé en tant que **copie dérivée** |
| PDF CEMAC original | non fourni | — |
| `audit-et-conception.md` | non fourni | — |

Les deux éditions sont publiées **pour consultation historique** uniquement. La publication opérationnelle est refusée, et l'API explique pourquoi : date d'effet non vérifiée, applicabilité non vérifiée, source dérivée, profil fiscal du lot 4 absent.

## Fonctionnalités réellement terminées

- **Modèle versionné** : source (empreinte SHA-256, provenance déclarée), exécution d'import (version de l'importateur, comptages, couverture), édition (dates d'effet inconnues par défaut, état brouillon / consultation / retirée), enregistrements bruts, nœuds, notes, observations de taux, occurrences, anomalies, corrections. Une relance crée un nouvel import et laisse l'ancien intact.
- **Import CSV** (DEV-006) : chaque ligne brute est conservée avec sa plage A1. Les codes restent en texte et gardent leurs zéros. Les codes mal formés sont bloqués, sans nœud. Les doublons sont gardés et signalés. Les parents SH (chapitre, position, sous-position) sont déduits sans libellé inventé. Chaque cellule fiscale devient une observation : valeur lue, inconnue si vide (≠ 0) ou non numérique. Sont aussi signalés : la colonne non numérique (TPM), les libellés aux caractères de contrôle (affichés « � », sans devinette) et l'absence de formules.
- **Import du classeur .xlsx** (DEV-006, REF-02) : lecture séparée des formules et des valeurs en cache (openpyxl). Aucune formule n'est évaluée et aucune liaison externe n'est ouverte : la cible est seulement relevée. Chaque observation garde sa formule d'origine. Sont signalés : la liaison vers un fichier absent, les colonnes calculées depuis ce fichier, les RECHERCHE dont la clé n'est pas le code de la ligne, et les nombres saisis comme texte. Un code saisi comme nombre (zéro perdu) est bloqué, jamais complété.
- **Import du texte du PDF** (DEV-007 partiel) : 551 pages conservées, avec page physique et numéro imprimé. Sont repérés les sections, chapitres et notes, les positions et lignes tarifaires avec leur page. Sont signalés les doublons, les codes mal formés, les codes lus sous une mauvaise position et la ponctuation parasite. **Aucun libellé ni taux n'est associé aux codes** : sans coordonnées, une association par ordre de lecture serait une supposition (conception §6.4).
- **Comparaison des sources** (REF-03) : chaque écart de code entre les deux éditions devient une anomalie à examiner. Aucune source ne « gagne ».
- **Recherche** (DEV-008, REC-01) : code exact, préfixe, texte intégral en français, puis trigrammes, chaque fois avec la raison du résultat. La recherche est filtrable par édition. Les zéros initiaux sont conservés et aucune complétion n'est faite.
- **Fiche d'un code** (REC-02) : chemin complet des parents (« Autres » reste dans son contexte), subdivisions et notes du chapitre et de la section. Les notes du même chapitre dans une autre édition sont étiquetées. La fiche montre aussi le même code dans les autres éditions, les observations de taux avec leur avertissement, les anomalies, les corrections et la **preuve** : ligne CSV ou page de texte, ouvrable à l'écran.
- **Administration** (DEV-009 partiel, REF-04/05/06) : liste des imports et anomalies filtrables, résolution motivée (acceptée, corrigée ou écartée). Une correction garde ancienne valeur, nouvelle valeur, justification et pièce, et ne modifie jamais le brut. Une édition publiée est immuable. Un retrait la sort de la recherche mais elle reste consultable par lien.
- **Interface** : onglet Référentiel avec recherche, fiche, preuve et avertissement « consultation historique ». Compte `referentiel@demo.demo` (gestionnaire du référentiel, sans société).

## Constats sur le classeur Excel d'origine

- Il contient une **liaison externe** vers `C:\DOCUMENTS ART\2015 APRES ISO\2015 TARIF EXCEL.xls` (feuilles « 2009 » et « 2015 »), absent.
- **STT** (F, 5 608 cellules), **TPM** (H, 4 458), TCI (I, 1) et OAD (K, 6) sont des formules `RECHERCHE` vers ce fichier. Leurs valeurs ne sont que des caches non vérifiables.
- Pour **TPM**, la clé de recherche est `'[1]2015'!A2` (une cellule du fichier absent) et non le code de la ligne `A2`. La valeur affichée peut donc venir d'un autre article. TPM contient d'ailleurs des unités (KGM, NMB…), pas des taux.
- CCI, OAD et TAUX sont saisis **comme texte** (environ 5 490 cellules chacun).
- Les **1 055 libellés abîmés** viennent du classeur lui-même (caractères de contrôle `_x0002_`, `_x0005_` à la place des accents). Ce n'est pas l'export CSV qui les a abîmés.
- Les codes sont identiques à ceux du CSV (5 609, zéros initiaux conservés, aucun doublon).

## Résultats sur les sources réelles (6 octobre 2026)

| | Classeur « 2016 » (.xlsx, comme le CSV) | Texte du PDF 2009 |
|---|---|---|
| Enregistrements bruts | 5 610 lignes (en-tête compris) | 551 pages |
| Lignes tarifaires | 5 609 | 5 446 |
| Autres nœuds | 6 374 parents déduits | 21 sections, 97 chapitres, 1 213 positions |
| Notes | — | 113 (sections et chapitres) |
| Pages avec codes | — | 382 ; 73 avant le tableau, 96 de texte seul |
| Anomalies principales | liaison externe, 4 colonnes issues de formules externes, clé TPM décalée, 1 055 libellés abîmés, 9 colonnes avec vides | 28 doublons, 21 codes mal formés, 21 codes sous une mauvaise position |
| Observations de taux | 38 829 lues, 12 803 inconnues, 4 458 non numériques | aucune (non associées) |

Comparaison : 5 364 codes communs, 82 présents seulement dans le texte du PDF, 245 seulement dans le classeur (327 anomalies `SOURCE_DIVERGENCE`).

Durée d'import mesurée : environ 8 s pour le .xlsx, 6 s pour le CSV et 2 s pour le texte. La recherche prend environ 100 ms par requête sur ces 2 éditions (mesure isolée sur la machine de développement, pas un p95 sous charge).

## Commandes

```bash
cd backend
python manage.py import_tariff_xlsx <fichier.xlsx> --label "Tarif intitulé 2016 (classeur original)" --note "…"
python manage.py import_tariff_csv  <fichier.csv> --label "Tarif intitulé 2016 (export CSV)" --note "…"
python manage.py import_tariff_text <fichier.txt> --label "Tarif CEMAC 2009 / SH 2007 (texte extrait)" --hs-version "SH 2007 (annoncé)"
python manage.py compare_tariff_editions <id édition A> <id édition B>
# publication (gestionnaire du référentiel) : POST /api/v1/tariffs/editions/<id>/publish {"mode": "consultation"}
```

## Tests exécutés

| Commande | Résultat |
|---|---|
| `python -m pytest` (backend) | 72 réussis (dont 28 pour le référentiel, jeu F et classeur fictif) |
| `ruff check .`, `ruff format --check .`, `makemigrations --check` | OK |
| `npm run typecheck`, `npm test`, `npm run build` | OK, 4 tests réussis |
| Import des trois sources réelles, comparaison, publication et parcours à l'écran | OK, captures livrées |

Correspondance avec la recette : T15 (chemin de « Autres », bonne édition), T29 (zéros), T30 (empreinte, édition, brut, formules et caches, liaison externe non exécutée), T31 (doublon, anomalie, correction séparée du brut), T32 (publication immuable, retrait, aucune activation opérationnelle implicite).

## Limites connues

- **PDF original nécessaire** : sans lui, pas d'extraction par coordonnées, donc ni désignations ni taux rattachés aux codes de l'édition 2009 (fin de DEV-007).
- Le fichier « 2015 TARIF EXCEL.xls » visé par les formules est nécessaire pour vérifier STT, TPM, TCI et OAD.
- La correspondance entre page physique et numéro imprimé est une hypothèse tirée des marqueurs du texte, à vérifier sur le PDF.
- Les 1 055 libellés abîmés du classeur ne sont pas réparés. Le motif (`\x02` → é, `\x05` → à) est probable mais non prouvé. Une correction en masse validée par un gestionnaire peut être ajoutée.
- La signification des colonnes DSO, STT, TPM et OAD n'est pas établie (TPM contient des unités). Elles restent des observations.
- Les renvois entre notes (« n° 03.01 ») ne sont pas encore résolus en liens. Les notes ne sont pas découpées en notes numérotées.
- Pas d'import par l'interface web : les imports passent par des commandes de gestion. L'upload arrive avec le stockage de pièces du lot 2.
- Les synonymes contrôlés et l'historique propre à une société (REC-03, P1) ne sont pas faits.

## Prochaine étape

Lot 2 : dossiers, pièces privées, lignes saisies et contrôle d'un code présent contre ces éditions. Si le PDF original arrive, reprendre DEV-007 avec pdfplumber avant le lot 3.
