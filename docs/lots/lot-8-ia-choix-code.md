# Lot 8 : l'IA choisit le code parmi les lignes du tarif

## Pourquoi

L'IA en ligne ne complétait que l'en-tête des pièces : l'utilisateur ne voyait pas de différence.
Le travail le plus long reste le code : un code à 6 chiffres (ou absent) oblige à choisir la
subdivision à 8 chiffres dans le tarif.

## Fonctionnalités terminées

- `apps/cases/ai_choice.py` : la recherche dans le tarif (sans IA) trouve les lignes candidates ;
  l'IA lit la désignation et choisit l'une d'elles en citant le passage qui la distingue, ou
  répond « information insuffisante ».
- Contrôles, quel que soit le fournisseur : ligne parmi les candidates, même code, passage cité
  présent dans la désignation ; sinon le choix est écarté et affiché comme tel, jamais réparé.
- Données envoyées : la désignation de la marchandise et les libellés du tarif seulement.
  Refus du client, société non activée et plafond mensuel (partagé avec le complément des
  pièces) appliqués avant tout envoi.
- Déclenchement : automatiquement après la lecture d'une facture (mode « automatique » de la
  société), pour chaque marchandise dont le code est incomplet, absent, introuvable ou ambigu ;
  ou sur demande, bouton « Demander à l'IA de choisir » dans l'aide au classement.
- Écran : « Choix de l'IA : code, libellé », raison, passage cité, bouton « Retenir le choix de
  l'IA ». La décision reste celle de l'agent (motif prérempli, modifiable) et garde la trace du
  choix (`evidence_refs` : `ai_choice`).
- Journal `AIClassification` append-only (statut, modèle, jetons, coût estimé, rejets).
- Adaptateurs Claude et Gemini : un seul appel structuré partagé (`_generate`) pour le
  complément des pièces et le choix du code.

## Limites

- Sans clé dans `donnees\ia.json` et sans activation dans Administration, IA en ligne, rien ne
  part : l'aide au classement reste la recherche dans le tarif.
- L'IA ne choisit que parmi les lignes trouvées par la recherche (10 au plus).
- L'origine, le régime et les taux ne sont jamais demandés à l'IA.

## Tests exécutés

- Backend : `tests/test_ia_choix_code.py` (T80) ; 339 tests, ruff, migrations.
- Frontend : `tests/ChoixIA.test.tsx` ; 75 tests, typecheck et build.

## Prochaine étape

Premier essai réel avec Gemini gratuit sur des pièces fictives, puis Claude.
