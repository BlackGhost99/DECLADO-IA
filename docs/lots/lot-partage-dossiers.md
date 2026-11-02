# Lot « Partage de dossiers entre sociétés » (COL-01 à COL-07)

Suite du lot multi-métiers (PR #75), demandé le 2 novembre 2026 : collaboration interentreprises. Un importateur partage un dossier avec son transitaire, un client avec son conseil, un transitaire avec un logisticien, sans casser l'isolation multi-sociétés.

## Fonctionnalités terminées

- **Code partenaire** (`apps.sharing.PartnerCode`) : un code par société, au format `CT-XXXX-XXXX` (sans 0/O ni 1/I). Il est lisible par les membres de la société, et seul l'administrateur peut le renouveler (l'ancien code devient alors inutilisable). Il n'y a pas d'annuaire : une société n'apprend l'existence d'une autre que si celle-ci lui donne son code.
- **Partage d'un dossier** (`CaseShare`) : un déclarant, un validateur ou un administrateur invite une société par son code, au niveau « lecture » ou « lecture et remarques », avec un message facultatif. Il ne peut y avoir qu'un seul partage en attente ou accepté par dossier et par société (contrainte en base).
- **Décision** : dans la société invitée, un validateur ou un administrateur accepte ou refuse. Avant l'acceptation, rien du dossier n'est lisible.
- **Retrait** : le propriétaire retire le partage, et l'accès cesse aussitôt.
- **Instantané** (`services.snapshot`) : le partenaire voit l'état, la révision, les pièces (type et nom, jamais le contenu), les factures, les marchandises avec les codes retenus et le n° de dépôt. Les écrans et endpoints de travail du dossier lui restent fermés (404).
- **Remarques** (`CaseShareNote`, en ajout seul) : les deux sociétés peuvent en écrire sur un partage « lecture et remarques ».
- **Journal** : la création, la décision, le retrait, chaque consultation par le partenaire et chaque remarque sont enregistrés dans l'audit des deux sociétés.
- **Interface** : un bloc « Partager avec une autre société » dans l'onglet Validation du dossier ; une entrée de menu « Partagés avec nous » (code partenaire, invitations reçues, acceptation ou refus, vue en lecture seule et remarques). Les écrans réutilisent les composants existants. Textes en FR, EN, ES et AR.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `backend/tests/test_partage.py` : T107 à T110, dont l'accès croisé d'une société tierce.
- `frontend/tests/Sharing.test.tsx` : invitation par code ; acceptation par un validateur mais pas par un déclarant ; code renouvelable par l'administrateur seul.

## Limites

- Pas encore de « prise en charge », où le transitaire recevrait une copie de travail du dossier d'un importateur. Le partage ne donne qu'une lecture.
- Le partenaire ne télécharge pas les pièces elles-mêmes, seulement leur liste.
- En installation hors ligne (un serveur par agence), le partage ne fonctionne qu'entre sociétés présentes sur le même serveur, jusqu'à la synchronisation centrale.

## Prochaine étape

Espace Importateur / exportateur : fournisseurs, commandes, estimation des droits, puis transmission du dossier au transitaire (prise en charge).
