# Lot « Fondations multi-métiers » (MET-01 à MET-06)

Demande du 2 novembre 2026 : rendre opérationnels les métiers Importateur, Logisticien et Conseil douanier, annoncés « Plus tard » dans la console, sur une architecture qui accueille d'autres professionnels du commerce international sans reconstruire l'application. Axe 2 « Multi-métiers & ClairTransit Core ».

Étude des métiers et des sources (Gabon/CEMAC, OMD, UE, États-Unis, ZLECAf) : document « ClairTransit — Importateur, logisticien, conseil douanier » (Claude Docs, lien donné dans le fil du projet).

## Principe retenu

Le métier dit ce qu'une société fait ; l'habilitation dit ce qu'elle a le droit de faire devant la Douane. Sources vérifiées le 2 novembre 2026 :

- [Douanes gabonaises, commissionnaires en douane](https://www.douanes.ga/particuliers/commissionnaires-en-douane) : propriétaire des marchandises (pour son compte), commissionnaire agréé pour autrui (CD CEMAC art. 148 à 151, Règlement 11/10-UEAC-207-CM-21), autorisation provisoire de dédouaner (art. 150), expert en douane agréé (Acte 3/96-UDEAC-1496-CD-57) qui conseille sans déclarer.
- [OMD, Convention de Kyoto révisée, chapitre 8](https://www.wcoomd.org/en/topics/facilitation/instrument-and-tools/conventions/pf_revised_kyoto_conv/kyoto_new/gach8.aspx) : déclarer soi-même ou par un tiers, conditions fixées par la loi nationale.
- [Code des douanes de l'Union, art. 18](https://www.legislation.gov.uk/eur/2013/952/article/18) et [19 CFR 111.2](https://www.law.cornell.edu/cfr/text/19/111.2) : représentation directe ou indirecte (UE), licence de courtier sauf importateur pour son propre compte (États-Unis).

## Fonctionnalités terminées

- **Quatre familles ouvertes** à la création d'une société (console et demande d'espace) : Transitaire / commissionnaire, Importateur / exportateur, Logistique et transport, Conseil et expertise douanière (libellés renommés en FR, EN, ES, AR).
- **Activités secondaires** (`OrganizationBusinessProfile.secondary_profiles`) : choisies à la création, modifiables ensuite par l'exploitant seul avec motif journalisé et contrôle de version (`PUT platform/organizations/{id}/profiles`).
- **Habilitations douanières** (`CustomsHabilitation`, propre à la société) : type, pays, référence en texte, dates de validité ; enregistrées « à vérifier » puis vérifiées ou retirées par l'exploitant avec motif (`platform/organizations/{id}/habilitations[/{hid}/verify|revoke]`). Un retrait est définitif. La société les lit dans `organization/overview`, sans pouvoir les modifier.
- **Capacités** (`business_permissions.organization_capabilities`) : réunion des capacités du métier principal et des activités secondaires. `declaration` est réservé au métier transitaire, ou à une habilitation déclarante vérifiée, en vigueur et du pays de la société. Exposées dans `me` (par société) et dans la console.
- **Contrôles serveur** : dépôt en douane (`workflow/lodge`) et export DAU refusés en `403 CAPABILITY_REQUIRED` sans la capacité ; l'export PDF d'une société non habilitée ne contient que le récapitulatif (plus de cases du DAU).
- **Interface** : choix des activités secondaires dans « Nouvelle société » ; panneau « Métiers et habilitations » dans la fiche d'une société (console) ; historique plateforme enrichi ; bouton « Marquer comme déposé en douane » et carte « Projet de déclaration » masqués quand la société n'est pas habilitée, avec une phrase qui l'explique. Le design existant n'a pas changé : composants et classes existants réutilisés.
- Migrations `organizations 0005` et `onboarding 0002` (libellés). Les sociétés existantes restent transitaires, sans changement de comportement.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `backend/tests/test_multi_metiers.py` : T103 (familles et activités secondaires), T104 (cycle d'une habilitation, pays, validité, retrait, accès croisé), T105 (capacités dans la session), T106 (importateur non habilité : pas de dépôt ni de DAU, PDF récapitulatif seul).
- `frontend/tests/CompanyManagement.test.tsx` : panneau métiers et habilitations (importateur sans déclaration, habilitation enregistrée « à vérifier », vérification impossible sans motif).
- Suite complète backend et frontend.

## Limites

- Les espaces propres à chaque métier ne sont pas encore construits : un importateur, un logisticien ou un conseil utilise aujourd'hui les écrans communs (dossiers, pièces, marchandises, calculs, contrôles, exports), sans DAU ni dépôt tant qu'il n'est pas habilité.
- Pas encore de partage de dossier entre sociétés (importateur ↔ transitaire, client ↔ conseil).
- Les habilitations sont saisies par l'exploitant après vue de l'acte : aucune vérification automatique auprès de la Douane, aucun justificatif stocké dans ClairTransit pour l'instant.
- Pays limités à la CEMAC ; les packs réglementaires d'autres régions restent à faire.

## Prochaine étape

1. Collaboration interentreprises : partage d'un dossier (lecture, remarques, prise en charge), acceptation, révocation, journal d'accès.
2. Espace Importateur / exportateur : fournisseurs, commandes, estimation des droits, transmission au transitaire.
3. Espace Logistique et transport : expéditions, conteneurs, étapes (BAE, enlèvement, livraison, retour vide).
4. Espace Conseil : études de classement, avis argumentés et sourcés, audit d'un lot de déclarations, rapports PDF.
