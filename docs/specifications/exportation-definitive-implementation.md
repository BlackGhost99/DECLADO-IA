# DECLADO IA — Contrat d'implémentation : exportation définitive (V1)

Statut : **spécification technique ; non activée en production**. Périmètre initial : Gabon, préparations douanières par société habilitée. À valider avec un professionnel et les textes nationaux avant calcul opérationnel.

## 1. Contexte vérifié dans main (2026-11-05)

- `backend/apps/cases/models.py` : `CustomsCase`, `CaseRevision` (mode, territoire, régime, état, bureau d'entrée), `CaseDocument`, factures et lignes, marchandises.
- `backend/apps/cases/api.py` : `CaseInput`, `revision_payload`, `case_payload`.
- `backend/apps/cases/services.py` : `create_case`, `update_revision`, vérifications de tenant et audit.
- `backend/apps/cases/revisions.py` : copie de révision validée ; la décision fiscale et les contrôles ne sont pas repris.
- `backend/apps/cases/completeness.py` : checklist actuelle d'importation, dont `importer` et `entry_office`.
- `backend/apps/fiscal/calculation.py` : calcul **import** de valeur douanière et taxes, fret/assurance selon Incoterm ; ne pas appeler pour l'export.
- `backend/apps/organizations/business_permissions.py` : capacité `declaration`, cumulée aux rôles et à l'isolation par société.
- `backend/apps/core/urls.py` : API `/api/v1/cases`, révisions, workflow, exports.

## 2. Règle métier

L'exportation définitive concerne des marchandises **en libre circulation** quittant le territoire douanier **pour y rester définitivement hors du territoire**. Ne pas confondre avec sortie temporaire, transit ou réexportation de marchandises sous régime particulier.

Références : OMD, Convention de Kyoto révisée, annexe spécifique C, chapitre 1 : https://www.wcoomd.org/fr/topics/facilitation/instrument-and-tools/conventions/pf_revised_kyoto_conv/kyoto_new/spanc.aspx?p=1 ; Douanes gabonaises, déclaration en détail import/export : https://www.douanes.ga/medias/documents/32/schema-de-dedouanement .

**Pas d'envoi électronique SYDONIA sans connecteur et autorisation officiellement validés.** Une validation DECLADO reste interne. Les pièces obligatoires, contrôles sectoriels, bureaux de sortie, taxes de sortie et codes de régimes nationaux devront être paramétrés sur des sources officielles datées.

## 3. Modèles et migration

Migration additive, compatible avec les dossiers existants :

- `CaseRevision.direction` : choix `import` / `export`, défaut `import` pour migration des dossiers historiques.
- `CaseRevision.procedure` : choix technique `import_general` / `export_definitive` (ou catalogue versionné de procédures) ; défaut `import_general`. **Ne pas confondre `regime` texte existant avec la direction** ; conserver `regime` pour le code local/produit validé.
- `CaseRevision.exit_office` : bureau de sortie (texte, facultatif en brouillon, obligatoire selon les règles nationales à validation).
- `CaseRevision.destination_country` : ISO 3166 alpha-2, pays de destination (requis pour l'export à la validation).
- `CaseRevision.exporter` : fiche `ExportParty` ou extension des acteurs commerciaux génériques, avec `organization` et invariants de société. Ne jamais détourner `CustomsCase.importer` pour représenter silencieusement l'exportateur.
- `CaseRevision.goods_free_circulation_confirmed` : booléen par défaut faux, preuve ou confirmation humaine auditée ; l'attestation seule ne dispense pas de pièces réglementaires.
- À terme : `ApplicableExportRule` versionnée (pays, période, SH, produit, source, exigences et taux) ; taux manquant = « inconnu », jamais 0 par défaut.

Invariant : `direction=export` implique `procedure=export_definitive` en V1 ; `direction=import` implique procédure import compatible. Les directions/procédures deviennent immuables dès qu'un dossier quitte l'état brouillon, sauf nouvelle révision contrôlée conservant l'historique.

IMPORTANT : revoir `revisions._clone` et l'héritage du nouveau couple direction/procédure ; une nouvelle révision d'un dossier validé conserve son sens, sans réutiliser les anciens calculs et validations.

## 4. Contrat API proposé

Réutiliser les routes existantes ; ne pas inventer de double API export :

- `POST /api/v1/cases` : ajouter `direction`, `procedure`, `exporter_id`, `destination_country`, `exit_office`. L'absence de `direction` reste `import` pour les clients existants.
- `GET /api/v1/cases` et `GET /api/v1/cases/{id}` : rendre `direction` et `procedure` visibles à tous les membres actifs autorisés ; `revision_payload` inclut les champs export.
- `PATCH /api/v1/revisions/{revision_id}` : mise à jour contrôlée des champs propres à l'export, avec `row_version` et audit.
- `GET /api/v1/cases/{id}/export-readiness` (nouveau) : `blocking[]`, `warnings[]`, `ruleset_version`, `as_of` ; refus fiable si règles réglementaires absentes.
- `GET /api/v1/cases/{id}/export-estimate` (nouveau) : tant qu'aucun barème export vérifié n'est configuré, réponse `status: unavailable`, `reason: EXPORT_RULES_NOT_CONFIGURED` ; jamais le résultat du calcul import.
- `POST /api/v1/cases/{id}/exports` : format spécifique `export_declaration_draft` distinct de tout document de liquidation/déclaration officiellement déposée ; marquage « projet — validation interne ».
- `POST /api/v1/cases/{id}/workflow/submit|validate` : réutiliser les transitions existantes, mais avec checklist adaptée au sens, contrôle de capacité et traçabilité.

Exemple de création :

```json
{
  "title": "Vente de bois transformé vers la France",
  "direction": "export",
  "procedure": "export_definitive",
  "territory": "GA",
  "destination_country": "FR",
  "transport_mode": "sea",
  "exit_office": "Bureau de sortie à confirmer"
}
```

Aucun code douanier national, taux ni pièce exigible n'est inféré dans cet exemple.

## 5. Permissions et séparation des responsabilités

- Lecture : membre actif de l'organisation propriétaire ou bénéficiaire d'un partage explicite, dossier par dossier.
- Création/édition : rôle déclarant / validateur conforme aux règles actuelles **et** capacité `declaration` côté serveur pour préparer une déclaration. Les sociétés importatrices sans habilitation peuvent seulement préparer des estimations ou dossiers non déclaratifs selon leur espace.
- Validation : appliquer la politique de séparation préparateur/validateur de l'organisation ; ne pas élargir les pouvoirs de l'administrateur ou de l'exploitant plateforme.
- Habilitation : vérifier agrément/autorisation en vigueur pour le pays et la date de l'opération avant tout export déclaratif. Le `declaration_basis=profile` actuel n'est **pas** une preuve d'agrément vérifié : combler cette faille de gouvernance avant mise en production.
- Tenant : tous les `exporter_id`, fichiers, marchandises, pièces et règles doivent appartenir à l'organisation ou à un référentiel public explicitement autorisé ; toute référence d'une autre société retourne 404.
- Audit : direction, procédure, destination, bureau de sortie, confirmation de libre circulation, décisions SH, validations, changements et export de fichier avec auteur et horodatage.

## 6. Checklist export définitive

Brouillon : autoriser la saisie partielle, indiquer les manques.
À la soumission/validation : bloquer si (1) exportateur absent, (2) destination absente, (3) libre circulation non vérifiée, (4) facture ou marchandises insuffisantes, (5) classement non validé, (6) conflits documentaires non résolus, (7) réglementations/politiques documentaires export nécessaires absentes ou non vérifiées, (8) autorisation sectorielle requise absente, (9) taux/fiscalité export requis inconnus.
Fournir un `code` machine stable pour chaque blocage. Les documents exigés dépendent du pays, du produit, de l'itinéraire et du régime ; pas de liste statique universelle.

## 7. Tests requis avant activation

**Migration** : dossiers existants gardent `direction=import`, API et exports import inchangés.
**Création** : export valide en brouillon, défaut import rétrocompatible, procédure incohérente rejetée 400.
**Workflow** : export incomplet autorisé en brouillon, soumission/validation refusée avec erreurs stables ; dossier complet validé en interne, jamais « accepté par la Douane ».
**Calculs** : export ne passe jamais par `fiscal.calculation.case_calculation` ni n'affiche des droits import ; absence de barème export = indisponible, pas zéro.
**Isolation** : accès, modification, attachement d'une pièce ou sélection exportateur inter-sociétés refusés.
**Permissions** : membre sans rôle, membre d'une autre société, expert sans habilitation, agrément expiré/refusé ; passage autorisé seulement après contrôles rôle+capacité+habilitation.
**Concurrence** : `row_version` périmée = conflit ; création de révision conserve direction et pièces, recalcul requis.
**Exports** : projet marqué comme tel, permissions et traçabilité, aucun dépôt automatique dans SYDONIA.
**Frontend** : type export sélectionnable uniquement si le serveur annonce la capacité et le workflow disponibles ; états de chargement, erreurs, i18n FR/EN/ES/AR.

## 8. Ordre d'implémentation

1. Migration additive + invariants modèles + tests de rétrocompatibilité.
2. Sérialiseurs, services, audit, API et tests d'isolation/perms.
3. Complétude/validation dédiées à l'export, sans réutilisation fiscale import.
4. Vue React création et détail, pièces/doc graph et étiquettes « Exportation définitive ».
5. Générateur de **projet** d'export, puis tests E2E ; mise en service derrière feature flag.
6. Validation terrain des exigences Gabon et de leur date de vigueur, avant activation opérationnelle.

## 9. Définition de terminé

Toutes les migrations, tests unitaires, intégration API, permissions, E2E et vérifications manuelles passent. Le feature flag n'est activé qu'avec référentiel réglementaire export vérifié et adapté au pays. Aucun impact régressif sur l'importation. Pas de fusion automatique sans vérification des contrôles CI.
