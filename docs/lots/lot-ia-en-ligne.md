# IA en ligne pour compléter les pièces : compte rendu de livraison

Date : 28 octobre 2026. Exigences : IAL-01 à IAL-10 (cahier des charges, « Extraction et contrôle documentaire »). Tests de recette : T58 à T67. Branche `ia-en-ligne`, au-dessus de `lecture-pieces`.

Demande : quand la lecture ne trouve pas une information sur une pièce, une IA en ligne peut la chercher dans le texte déjà lu. Décisions de l'utilisateur :
- service en ligne, désactivé par défaut ;
- un client peut refuser, et son refus l'emporte sur le réglage de la société ;
- Claude (Anthropic) pour l'usage réel ;
- Gemini gratuit pour les essais, sur des pièces fictives uniquement ;
- sans IA, la lecture et la saisie continuent comme avant.

La maquette validée avant le code est publiée : https://claude.ai/artifact/JQFkpvLaWaK26iTaDTw3wD.

## Fonctionnalités terminées

- **Deux verrous** (IAL-01, IAL-02, IAL-10) :
  - l'exploitant pose la clé sur le serveur (`donnees\ia.json` sous Windows, ou les variables `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` et `AI_FREE_TIER`) ;
  - l'administrateur de la société active ensuite l'IA dans Administration > IA en ligne ;
  - sans clé, l'interrupteur reste grisé et le serveur refuse l'activation ;
  - la clé n'est jamais renvoyée au navigateur ni écrite dans un journal.
- **Ce qui part** (IAL-03, IAL-04) :
  - on envoie le texte lu de la pièce concernée, avec ses repères « [page N] », son type et la liste des informations non trouvées ;
  - ni le fichier, ni les autres pièces, ni les noms des agents ne partent ;
  - une information déjà lue, déjà proposée, déjà saisie, ou déjà demandée sur la même lecture n'est pas redemandée.
- **Contrôle des réponses** (IAL-05, IAL-06) :
  - la réponse suit un schéma strict ;
  - une proposition est écartée, et jamais réparée, quand son extrait est introuvable dans la pièce, quand sa valeur n'est pas dans l'extrait, ou quand elle est en double ou non demandée ;
  - « non trouvé » est toujours accepté ;
  - la consigne demande de traiter la pièce comme une donnée et de ne jamais proposer de code SH, de taux, de droit ou de taxe ;
  - quand le fournisseur échoue (clé refusée, saturation, réseau, refus, réponse illisible), la lecture aboutit sans proposition et l'échec est journalisé ;
  - aucun repli vers un autre fournisseur.
- **Refus du client** (IAL-07) :
  - la colonne « Lecture par IA » et le bouton « Modifier » se trouvent dans Administration > Importateurs ;
  - un agent ou l'administrateur pose le refus ; seul l'administrateur le lève ;
  - chaque changement est journalisé avec son auteur ;
  - sur la pièce, l'écran affiche « Non envoyée à l'IA ».
- **Plafond et coût** (IAL-08) :
  - plafond mensuel de pièces envoyées par société (200 par défaut) : une fois atteint, rien ne part et la lecture continue ;
  - le coût estimé vient des prix publics relevés le 28/10/2026 ;
  - il est inconnu, jamais zéro, pour un modèle sans prix connu ;
  - l'offre gratuite est signalée.
- **Propositions sur la pièce** (IAL-09) :
  - chaque proposition est marquée « Proposé par l'IA · À vérifier », avec l'extrait cité et « Voir la source » ;
  - pour un titre de transport, une assurance ou une facture de fret, l'agent peut accepter, corriger ou saisir une information non trouvée ;
  - pour une facture, la proposition ne remplit la fiche qu'après acceptation, comme une correction attribuée ;
  - en mode « sur demande », un bouton « Compléter avec l'IA » s'affiche quand des informations manquent.
- **Journal des envois** (IAL-10) : les 30 derniers envois, avec dossier, pièce, informations demandées et trouvées, coût et statut. Il n'est pas modifiable. L'audit compte les informations sans recopier les valeurs.
- **Adaptateurs** :
  - `apps/extraction/ai_providers.py` est le seul endroit où un SDK est importé (`anthropic==2.3.0`, `google-genai==2.33.0`) ;
  - modèles par défaut : `claude-haiku-5-5` et `gemini-3.5-flash-lite`.
- **Langues** : textes en français, anglais, espagnol et arabe (`frontend/src/i18n/ia.ts`). L'arabe s'affiche de droite à gauche.

## Ce que l'exploitant doit faire

1. Créer une clé Claude sur https://console.anthropic.com (rubrique API Keys) et y ajouter un moyen de paiement.
2. Sur le serveur, créer `donnees\ia.json` dans le dossier d'installation : `{ "fournisseur": "anthropic", "cle": "sk-ant-..." }`. Pour des essais sur des pièces fictives seulement : `{ "fournisseur": "gemini", "cle": "AIza...", "gratuit": true }`, avec une clé gratuite de Google AI Studio.
3. Relancer `demarrer-clairtransit.ps1`. Le script affiche « IA en ligne disponible », sans la clé.
4. Dans ClairTransit, l'administrateur de la société active l'IA (Administration > IA en ligne) et marque les clients qui refusent (Importateurs).
5. Faire valider par le conseil de la société le contrat du fournisseur, la conservation des données et le transfert hors du Gabon.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

Migrations : `extraction/0002_ia_en_ligne` (texte lu, réglage de la société, journal des envois) et `clients/0002_ia_en_ligne` (refus du client).

## Tests exécutés

- Backend : 290 tests réussis, dont 16 dans `tests/test_ia_en_ligne.py` (T58 à T66) et 4 dans `tests/test_ia_adapters.py` (T67). Aucun appel réel :
  - un fournisseur factice remplace l'adaptateur ;
  - les adaptateurs utilisent la vraie bibliothèque Claude ou Gemini contre un serveur HTTP local.
- Frontend : 52 tests réussis, dont 8 dans `tests/IAEnLigne.test.tsx`, avec contrôle des quatre langues. Typecheck et build réussis.
- Parcours dans l'application, avec un fournisseur factice local :
  - activation par l'administrateur ;
  - B/L fictif lu : 10 informations demandées, 2 proposées avec leur extrait ;
  - proposition acceptée, puis valeur saisie ;
  - refus d'un client ;
  - écran en arabe.
- Script Windows : analyse PowerShell sans erreur. Le bloc `ia.json` a été essayé avec Claude, Gemini gratuit et un fournisseur inconnu (ignoré).

## Limites

- Aucun appel réel n'a encore été fait : il faut la clé de l'exploitant. Le premier essai réel doit se faire avec Gemini gratuit, sur les pièces fictives BatiPro.
- Les pièces scannées sans texte (images) passent d'abord par l'OCR local ; l'IA ne reçoit que le texte obtenu.
- Le coût affiché est une estimation à partir des jetons ; la facture réelle vient du fournisseur.
- Le lieu de traitement et la conservation sont affichés comme « à vérifier » : ils dépendent du contrat de l'exploitant.
- Les lignes de marchandises d'une facture ne sont pas complétées par l'IA, seulement l'en-tête.

## Prochaine étape

Premier essai réel avec la clé Gemini gratuite sur les pièces fictives, puis avec la clé Claude. Ensuite, décider si l'IA aide aussi à résoudre les relations entre pièces (graphe documentaire), toujours en proposition à vérifier.
