# Mise en route — installation neuve, console de l'exploitant et invitations : compte rendu de livraison

Date : 24 octobre 2026. Exigences : ACC-04 à ACC-08 (cahier des charges, « Comptes, sociétés et importateurs »). Tests de recette : T46 à T50.

Demande : « l'application est toujours fictive, l'ouverture dirige droit vers un compte fictif ; au début tout doit être neuf ». Choix validé : ouverture hybride des sociétés (créées par l'exploitant depuis sa console, ou demandées publiquement puis acceptées par lui). La maquette en huit écrans a été validée avant le code. Le design existant ne change pas : les nouveaux écrans reprennent ses composants.

Démonstration, déroulée dans Chromium sur une base vide :
1. Le premier écran est « Mise en service de ClairTransit ». Il crée le compte de l'exploitant, puis exige la double authentification.
2. La console « Sociétés clientes » permet à l'exploitant de créer « Transit Exemple SARL » ; un lien d'activation à copier s'affiche.
3. L'administratrice invitée ouvre ce lien et choisit elle-même son mot de passe. La double authentification est ensuite obligatoire pour elle.
4. Elle arrive sur un tableau de bord vide qui propose « Créer mon premier dossier ». Le bloc « Mise en route » l'invite à ajouter une agence puis des collaborateurs.
5. Elle crée l'agence « Libreville Port » et invite un déclarant rattaché à cette agence. Le lien du déclarant s'affiche, et son invitation apparaît comme « Invitation envoyée ».
6. Une demande d'espace envoyée depuis l'écran de connexion (« Demander l'ouverture ») apparaît dans la console avec Accepter et Refuser.

Toutes les étapes ont été vérifiées en français et en arabe (RTL), et à 400 px de large sans défilement horizontal.

## Fonctionnalités terminées

- **Installation neuve** (ACC-04) :
  - tant qu'aucun compte n'existe, l'API publique `GET/POST /auth/setup` affiche puis crée le compte de l'exploitant ;
  - ce compte ne peut être créé qu'une fois : verrou PostgreSQL, puis 409 `SETUP_DONE` ;
  - l'exploitant gère aussi le référentiel ;
  - sa double authentification est exigée côté serveur, quel que soit `MFA_ENFORCE`.
- **Demande d'espace** (ACC-05) :
  - formulaire public, limité en débit, qui ne crée aucun compte ;
  - seul le profil Transitaire est ouvert (Importateur, Logisticien et Conseil sont annoncés « plus tard ») ;
  - seuls les pays CEMAC sont acceptés ;
  - en cas d'acceptation, la société est créée et son contact est invité comme administrateur ;
  - un refus doit être motivé ;
  - chaque décision est journalisée.
- **Console de l'exploitant** (ACC-06) :
  - sociétés avec leur profil, pays, sièges utilisés sur sièges prévus et état ;
  - « Nouveau lien » tant que l'administrateur n'a pas activé son compte ;
  - Suspendre et Réactiver ;
  - aucune route de la console n'ouvre un dossier, une pièce ou un importateur.
- **Invitations** (ACC-07) :
  - jeton aléatoire ; seule son empreinte SHA-256 est gardée ;
  - valable 72 heures, à usage unique, renouvelable ; un renouvellement ou une nouvelle invitation à la même adresse invalide l'ancien lien ;
  - lien refusé s'il est expiré, utilisé, annulé ou si la société est suspendue ;
  - l'invité choisit lui-même son mot de passe ; un compte existant se rattache avec son propre mot de passe ;
  - le lien se copie à la main : aucun e-mail n'est nécessaire, donc l'application fonctionne sans internet.
- **Administration de la société** (ACC-08) :
  - onglet Agences ;
  - onglet Utilisateurs : membres et invitations en attente, agence modifiable, désactivation et réactivation, renouvellement et annulation des invitations, formulaire d'invitation avec rôles et agence ;
  - limite de sièges (`SEAT_LIMIT`), qui compte les membres actifs et les invitations en attente ;
  - le propre compte de l'administrateur ne propose pas « Désactiver » ;
  - les premiers pas restent sur le tableau de bord tant que les agences et l'équipe ne sont pas en place.
- **Modèles métiers** :
  - `OrganizationBusinessProfile` et `Agency` reprennent tels quels les modèles de la PR #7 (multi-métiers), qui n'est pas fusionnée ;
  - `business_permissions.py` est copié de la PR #7 ;
  - la migration donne le profil Transitaire aux sociétés existantes.
- **Script Windows** :
  - installation neuve par défaut ;
  - `-Demo` ajoute les comptes et le référentiel fictifs ;
  - clés `DJANGO_SECRET_KEY` et `MFA_ENCRYPTION_KEY` générées une fois sur le PC, dans `donnees\cles.json`, jamais dans le dépôt ;
  - branche par défaut : `mise-en-route`.
- **Journal d'activité** : libellés en quatre langues pour les nouveaux événements.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- **Backend** : 249 tests réussis, dont 18 dans `tests/test_onboarding.py` :
  - mise en service unique et double authentification exigée ;
  - console fermée aux administrateurs de société et aux anonymes ;
  - aucune donnée de société visible par l'exploitant ;
  - demande acceptée ou refusée ; profils et pays fermés ;
  - suspension et réactivation ;
  - renouvellement ;
  - invitation d'un agent, compte existant, règles de lien (expiré, utilisé, annulé, société suspendue) ;
  - limite de sièges ;
  - isolation entre sociétés (404) ;
  - réactivation et changement d'agence.
- **Frontend** : 37 tests réussis, dont 5 dans `tests/Onboarding.test.tsx` (mise en service, lien « Demander l'ouverture », activation, lien périmé, console avec acceptation et lien affiché). Le test i18n vérifie que les clés sont les mêmes dans les quatre langues.
- **Parcours complet dans Chromium** sur une base vide, comme décrit ci-dessus.

## Limites

- Une installation existante avec la démonstration garde ses comptes fictifs et n'a pas d'exploitant : il faut repartir d'un nouveau dossier (`-Dossier`). La mise en service n'est proposée que si aucun compte n'existe, pour ne pas ouvrir la création d'un exploitant sur un serveur déjà en service.
- Pas d'envoi d'e-mail : le lien est copié et transmis par l'exploitant ou l'administrateur.
- Les profils Importateur, Logisticien et Conseil sont visibles mais fermés.
- Le partage importateur et transitaire n'est pas traité.
- Les agents peuvent remettre la double authentification à plus tard si `MFA_ENFORCE` est désactivé (cas du PC local) ; elle est imposée en production.
- Sur une installation neuve, le référentiel tarifaire est vide jusqu'à l'import de la source officielle.

## Prochaine étape

- Fusionner cette branche après la refonte et la numérisation.
- Reprendre la PR #7 (multi-métiers) sur ces modèles.
- Ajouter la synchronisation entre serveur d'agence et serveur central.
