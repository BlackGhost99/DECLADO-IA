# Taxes et règles : compte rendu de livraison

Date : 29 octobre 2026. Exigences : TAX-01 à TAX-07 (cahier des charges, « Valorisation et calcul »). Tests de recette : T20 à T22 et T68 à T71. Branche `taxes-et-regles`, partie du lot 4.

Demande : remplir l'écran « Taxes et règles », vide jusque-là, avec les vraies taxes et les vrais taux, puis faire le calcul. Décisions de l'utilisateur (29/10/2026) :
- la base est le classeur **Tarif CEMAC 2022 SWD** ; seul le droit de douane change souvent, il dépend du code SH ;
- seul l'admin ClairTransit (gestionnaire du référentiel) modifie un taux ;
- la redevance informatique est un pourcentage ; son taux et sa base restent à confirmer ;
- la TCI a un mode de paiement à part sur la déclaration vérifiée : sa prise en compte dans le total est en attente ;
- la maquette est validée.

## Règles vérifiées

Les bases viennent de la formule « Taux cumulé » du classeur 2022 :
- DDI, TCI, CCI, OAD et CAF sur la valeur ;
- DA sur valeur + DDI ;
- TVA et CSS sur valeur + DDI + DA.

Elles ont été vérifiées sur une déclaration réelle (base 549 070 FCFA, DDI 10 %). Chaque taxe, arrondie au franc supérieur, redonne le montant de la déclaration :

| Taxe | Montant |
|---|---|
| DDI | 54 907 |
| TVA | 108 716 |
| TCI | 5 491 |
| CCI | 2 197 |
| OAD | 275 |
| CSS | 6 040 |
| CAF | 1 099 |

La déclaration n'est pas dans le dépôt : seuls ces chiffres, sans donnée client, servent de test. La « redevance statistique » de l'ancien écran n'existe pas : elle est retirée. Le DSO (droit de sortie) est montré « export seulement » et n'entre pas dans un calcul d'importation.

## Fonctionnalités terminées

- **Import du classeur SWD** (TAX-01, commande `import_tax_schedule`) :
  - feuille 1 : une ligne par code à 8 chiffres et sous-position nationale ; chaque taux est gardé tel que lu avec sa cellule (ex. `G120`) ;
  - feuille 2 (TEC SH 2022) : lue pour comparaison seulement, jamais appliquée ;
  - le même import crée l'édition du référentiel (recherche, libellés) avec la ligne « 000 » de chaque code ; la preuve garde la vraie plage de la feuille ;
  - un nouvel import active le nouveau barème pour le Gabon et garde l'ancien ; chaque activation est journalisée.
- **Résolution datée des taux** (TAX-01, TAX-03) :
  - la ligne « 000 » du code fait foi ;
  - sans elle, un taux identique sur toutes les sous-positions vaut pour le code ; sinon il reste inconnu (« sous-position à préciser ») ;
  - une cellule vide est un taux inconnu, jamais 0 ; seule l'accise vide signifie « pas d'accise ».
- **Modifications de taux** (TAX-04, `POST /api/v1/fiscal/amendments`) :
  - réservées à l'admin ClairTransit (403 pour une société) ;
  - taxe, portée (ce code ou tous les codes), nouveau taux, date d'effet, type de texte, référence et motif ; la référence est facultative pour une « décision de l'exploitant » ;
  - ajout seul : le barème importé et les modifications ne sont jamais réécrits ; chaque ajout est journalisé et crée la version suivante des taxes ;
  - la dernière modification en vigueur à la date l'emporte ; avant sa date d'effet, l'ancien taux reste appliqué.
- **Moteur de calcul** (TAX-02, TAX-06) :
  - fonctions pures en Decimal ;
  - une valeur ou un taux inconnu rend inconnues la taxe et celles qui en dépendent ;
  - le total n'est donné que s'il est complet ; sinon la somme connue est affichée « incomplet ».
- **Valeur en douane d'un dossier** :
  - lignes de facture affectées à la marchandise, frais et remises de la facture répartis au prorata de la valeur ;
  - fret et assurance des pièces ajoutés selon l'incoterm : rien pour CIF/CIP, l'assurance pour CFR/CPT, les deux pour EXW/FCA/FAS/FOB ; ils sont répartis selon la valeur ;
  - pièce absente ou montant non lu : calcul provisoire avec la raison ;
  - XAF et EUR (parité fixe 655,957) seulement ; une autre devise donne une valeur inconnue (« taux de change à saisir »).
- **API** :
  - `GET fiscal/taxes` (vue d'ensemble, `can_edit`) ;
  - `GET fiscal/taxes/review/<liste>` ;
  - `GET fiscal/rates?code=` ;
  - `GET/POST fiscal/amendments` ;
  - `GET cases/<id>/calculation` (bornée à la société, 404 sinon).
- **Écrans**, selon la maquette validée, avec les composants existants :
  - onglet « Taxes et règles » : taxes, assiettes, taux, source, état, bouton « Modifier » pour l'admin seulement, formule, lignes à revoir avec leur liste, historique ;
  - fiche d'un code : taux applicables aujourd'hui avec leur cellule, taux cumulé, écart avec le TEC, « Modifier un taux » pour l'admin ;
  - formulaire de modification ;
  - calcul du dossier : taxes, base, montant, total, détail par marchandise, notes « provisoire » et « incomplet » ;
  - textes en FR, EN, ES et AR (`i18n/taxes.ts`).
- **Script Windows** : `-ImporterTarif` reconnaît un classeur SWD et appelle `import_tax_schedule`, puis publie l'édition en consultation.

Sur le classeur réel : 6 252 lignes, 6 076 codes, 56 268 taux lus. À revoir :
- 34 lignes au DDI différent du TEC (`/mnt/project-files/clairtransit/tarif/ecarts-droit-douane-2022-swd-tec.csv`). La maquette en annonçait 76, mais 38 étaient « EXO » contre 0 % : ce ne sont pas des écarts ;
- 75 lignes avec une taxe vide ;
- 208 lignes de sous-positions nationales.

## Commandes

```
cd backend && python manage.py import_tax_schedule "Tarif_CEMAC_2022_SWD.xlsx"   # active le barème pour GA
cd backend && python manage.py publish_tariff_edition --label "Tarif CEMAC 2022 (SWD)"
```

Sous Windows : `demarrer-clairtransit.ps1 -ImporterTarif <chemin du classeur>`.

## Tests exécutés

- `cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest` : 312 tests passés, dont 15 dans `tests/test_fiscal.py`.
- `cd frontend && npm run typecheck && npm test && npm run build` : 60 tests passés, dont 4 dans `tests/Taxes.test.tsx`.
- Contrôle visuel sur le classeur réel importé et le dossier de démonstration DOS-2026-0007 (données fictives).

## Limites

- **Redevance informatique** : calculée par SYDONIA selon ses propres critères, montant non fixe (réponse d'un déclarant, 30/10/2026). ClairTransit ne la calcule pas, ne la compte pas dans le total et n'accepte pas de taux saisi pour elle.
- **TCI** : versée sur un compte à part (compte 2) ; elle est affichée à part et n'entre pas dans le total de l'article (30/10/2026). Le total de l'article de la déclaration vérifiée, 173 234, est retrouvé. Version des règles : `2022-swd-2`.
- **Calcul non figé** : il est refait à chaque ouverture du dossier. L'enregistrement d'un calcul validé, avec sa version, vient avec le circuit de validation (lot 5).
- **Exonérations et régimes** : les exonérations conditionnelles (TAX-04 au sens des exemptions), les régimes particuliers et l'origine ne sont pas encore modélisés. La TVA à 0 % du barème est appliquée telle que lue.
- **Sous-position nationale** : elle n'est pas encore choisie dans le dossier. Un code à sous-positions aux taux différents reste inconnu pour ces taxes.
- **Devises** : seuls le XAF et l'EUR sont convertis. La saisie d'un taux de change daté reste à faire (DEV-020).
- **Texte joint** : le PDF du texte officiel ne se joint pas encore à une modification ; la référence écrite est enregistrée.
- **Langue** : les raisons calculées par le serveur (« Taux inconnu. », pièces absentes…) restent en français.

## Prochaine étape

1. ~~Redevance informatique et TCI~~ : réglé le 30/10/2026 (RI par SYDONIA, TCI au compte 2).
2. Saisir le taux de change d'une autre devise et choisir la sous-position nationale dans le dossier.
3. Figer le calcul à la validation (lot 5) et l'exporter avec sa version.

## Import depuis l'écran (30/10/2026, T78)

Le gestionnaire du référentiel importe désormais le tarif depuis Référentiel > Administration tarifaire > Import Excel, sans ligne de commande. Le fichier (.xlsx ou .csv, 40 Mo au plus) passe par la quarantaine et ClamAV, puis l'importeur adapté : un classeur « Tarif CEMAC SWD » importe aussi le barème des taxes et l'active pour le Gabon. L'édition est publiée en consultation. Le script Windows (`-ImporterTarif`) reste possible et fait la même chose.
