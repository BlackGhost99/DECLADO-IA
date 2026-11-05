# Vérification du brief Gemini — exportation définitive (05/11/2026)

Ce document complète `exportation-definitive-implementation.md`. Les affirmations du brief utilisateur ne sont **pas automatiquement des règles applicables**. Toute règle doit porter un pays, un produit, une période de validité, une source officielle et une version.

## Règles vérifiées

- BEAC, règlement n° 02/18/CEMAC/UMAC/CM art. 53 et 55 ; instruction 006/GR/2019, art. 6 et 9 : domiciliation de certaines exportations au moins égales à **5 000 000 XAF** et rapatriement des recettes des ventes fermes au plus tard **150 jours** après exportation. Tenir compte des exceptions et de la nature de l'opération. Sources : https://www.beac.int/wp-content/uploads/2016/10/Instruction-n%C2%B0-006-GR-2019.pdf ; https://www.beac.int/wp-content/uploads/2020/06/REGLEMENT-02-18-CEMAC-UMAC-CM_001.pdf .
- Conseil gabonais des chargeurs : BIETC pour les modes maritime, aérien, terrestre et ferroviaire, selon leurs procédures. Source : https://cgcgabon.ga/encadrement-du-trafic/ .
- Gabon, loi n°041/2025 du 30 décembre 2025, loi de finances 2026, art. 5-7 : bois transformé 1ère transformation **15 % de la valeur mercuriale**, 2e **10 % de la valeur mercuriale**, 3e **3,5 % de la valeur FOB** ; lingots d'or **1 % de la valeur en douane à l'exportation**. Source : https://journal-officiel.ga/22265-041-2025-/ . Les pages génériques plus anciennes des Douanes présentent d'autres taux : ne pas préférer ces anciens barèmes à une loi publiée plus récemment sans examiner les dates d'effet et exceptions.

## Affirmations du brief à ne pas coder en dur

- « Toute exportation a une TVA à 0 % » : qualification fiscale spécifique à confirmer.
- « Toute exportation se taxe sur la base FOB » : faux pour les bois de 1ère et 2e transformations en 2026 (base mercuriale). La décomposition CIF en FOB n'est possible que lorsque fret/assurance sont justifiés et que le référentiel applicable réclame cette base.
- « EUR.1 pour chaque export vers l'UE » : dépend des arrangements préférentiels réellement applicables ; ne pas proposer EUR.1 automatiquement pour le Gabon. Sources https://taxation-customs.ec.europa.eu/customs/rules-origin-goods/preferential-rules-origin/proof-origin_en et https://taxation-customs.ec.europa.eu/list-non-eu-countries_en .
- « EX1/EX2 » : ne pas présumer le code national exact à partir du sens export seul ; vérifier le régime et la version de SYDONIA.
- « BIETC obligatoire pour tous les exports sans exception » : vérifier les exceptions, l'assujettissement et les formalités selon type de marchandise et mode de transport.
- Restrictions sectorielles (bois brut, mines, produits agricoles) : sources officielles sectorielles requises pour le déclenchement d'une interdiction ou obligation bloquante.
- Exemple JSON Gemini : son taux de **3 % sur bois scié** n'est pas un barème générique applicable en 2026. Pour un dossier `value_fob_xaf=29518065`, ne jamais produire automatiquement `885542 XAF` de droits sans classifier le stade de transformation, identifier la base et la période réglementaire.

## Impacts pour le développement

1. Ajouter sous-modules `export_fx_obligations` : banque domiciliataire, date effective de sortie, pièces de change, échéance 150 jours conditionnelle, état d'apurement bancaire — **sans prétendre vérifier auprès de la BEAC**.
2. Ajouter `export_certifications` : justificatifs phytosanitaires/sectoriels et certificat d'origine conditionnels, avec preuves et validation humaine.
3. Ajouter `export_cargo_tracking` : BIETC, transport, référence de déclaration, preuves de mainlevée/embarquement, date de sortie ; enregistrer les événements, ne pas les inventer.
4. Le moteur export doit résoudre **taux + assiette** (FOB, mercuriale, autre) par article, stade de transformation, pays, période et source. Si source ou valeur mercuriale inconnue : résultat **indisponible**, jamais taux 0 par défaut.
5. Contrôles de rapprochement OCR : facture, colisage (poids/volume), B/L ou LTA, conteneurs, engagement de change, BIETC ; alertes avec provenance de chaque preuve.
6. Prévoir tests BEAC : 4 999 999 vs 5 000 000 XAF ; dispenses ; échéance calculée sur date effective de sortie ; tests de taux bois 15% mercuriale / 10% mercuriale / 3,5% FOB ; règle future et historiques ; refus d'un EUR.1 sans arrangement applicable.

**Sécurité** : documents bancaires et flux commerciaux sensibles ; tenant isolation, permissions au moindre privilège, antivirus, audit, séparation métier/statut douanier. **État** : note documentaire, aucune fonctionnalité activée ou test exécuté.
