# Lot 7 : préparation automatique du dossier

## Pourquoi

Après la lecture d'une facture, l'agent devait encore remplir à la main la date de déclaration,
le régime, l'édition du référentiel, créer les marchandises, lancer chaque contrôle de code et
saisir l'origine ligne par ligne. Les Contrôles affichaient 7 points bloquants sur un dossier
pourtant lu correctement.

## Fonctionnalités terminées

- `apps/cases/autoprep.py`, appelé après chaque lecture réussie d'une facture, dans la même
  transaction mais sans pouvoir l'annuler (un échec est journalisé, la lecture reste).
  Seuls les champs vides sont remplis, jamais une saisie d'agent :
  - édition du référentiel : la plus récente publiée et visible, opérationnelle d'abord ;
  - date de déclaration prévue : aujourd'hui ;
  - régime : celui du dernier dossier de la société, s'il en existe un ;
  - origine du dossier : seulement si la facture l'imprime (libellé « Country of origin » /
    « Pays d'origine », ou un seul pays « Made in … » dans tout le texte) ;
  - une marchandise par ligne facturée libre, puis le contrôle de son code.
- `CaseRevision.prefilled` (migration 0009) : la date, le régime et l'édition proposés restent
  « Proposé automatiquement, à confirmer » jusqu'à ce qu'un agent les enregistre. Les Contrôles
  le signalent en « à vérifier », pas en bloquant.
- Origine des marchandises au niveau du dossier : saisie une fois dans l'Aperçu, elle vaut
  pour toutes les marchandises sans origine (`goods_line.origin_from_case` journalisé). Une
  ligne facturée rattachée n'est plus signalée en double : l'origine manquante est signalée
  une seule fois, sur la marchandise.
- Écran : bandeau et mention sous chaque champ proposé, champ « Origine des marchandises »,
  textes FR/EN/ES/AR.

## Limites

- L'origine n'est jamais devinée : sans mention dans la pièce, elle reste à saisir (une fois
  par dossier suffit).
- Un code à 6 chiffres reste « subdivision à choisir » : aucun zéro n'est ajouté, la liste
  des subdivisions est proposée comme avant.
- Le régime n'a pas encore de valeur par défaut configurable par société : il est repris du
  dernier dossier.

## Tests exécutés

- Backend : `tests/test_preparation_auto.py` (T79), `test_proposals.py` adapté ; 332 tests.
- Frontend : `tests/PreparationAuto.test.tsx` ; 73 tests, typecheck et build.

## Prochaine étape

Régime par défaut et bureau d'entrée configurables par société ; proposition d'origine à
partir d'un certificat d'origine joint au dossier.
