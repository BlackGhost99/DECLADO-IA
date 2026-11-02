# Lot : confirmation groupée des codes et archive complète du dossier

Suite du circuit de validation (lots 5 et 6). Branche `claude/project-thread-yib6vz`, base `main` après #58.

## Fonctionnalités terminées

- **Confirmation groupée, tout ou rien** (T77, COD-03, COD-07). Le bouton « Confirmer les codes reconnus (n) » de l'onglet Marchandises existait depuis #46 mais envoyait une décision par marchandise, l'une après l'autre : une erreur au milieu laissait le dossier à moitié confirmé.
  - Nouvel envoi unique `POST /api/v1/revisions/{id}/code-confirmations` (`reason`, `items[]` : marchandise, contrôle, version de la ligne, `node_id` pour un complément).
  - Chaque élément passe par `services.record_decision` : contrôle à jour, code retrouvé, version de la ligne ; une décision attribuée, motivée et liée à son contrôle par marchandise, journalisée (`goods_line.code_decided`), plus un événement `goods_line.codes_confirmed` pour l'ensemble.
  - Une seule erreur annule tout ; le message nomme la marchandise (« Marchandise 2 : … Aucun code n'a été confirmé. »).
  - Code incomplet : accepté seulement avec la subdivision unique offerte par le tarif, vérifiée comme complément.
  - Au plus 500 marchandises par envoi ; doublon, motif vide, marchandise d'un autre dossier ou d'une autre société refusés.
- **Archive complète du dossier** (EXP-04, T84). Le bouton « Télécharger le dossier complet » de l'onglet Export, désactivé jusqu'ici, produit un ZIP `REF_dossier_complet[_brouillon].zip` :
  - `revision-N/pieces/` : pièces originales, octets conservés après l'antivirus ; `pieces-remplacees/` pour la traçabilité ;
  - `revision-N/exports/` : projets DAU, récapitulatifs PDF et détails Excel conservés ;
  - `revision-N/circuit-validation.csv`, `decisions-codes.csv`, `calcul-valide.json` (calcul figé à la validation interne) ;
  - `journal.csv` (historique complet, cellules neutralisées contre les formules), `LISEZMOI.txt`, `manifeste.json` (empreinte SHA-256 de chaque fichier ; l'empreinte d'origine de chaque pièce et export est revérifiée, un écart est signalé).
  - Si la révision courante n'a pas encore de projet DAU et d'Excel pour son calcul actuel, ils sont générés, conservés et journalisés comme tout export ; une deuxième archive n'en recrée pas.
  - Téléchargement journalisé (`case.archive_downloaded`, avec l'empreinte du ZIP). Rappel dans l'archive : validé en interne, jamais une acceptation par la Douane.
  - Rôles : déclarant, validateur, administrateur de la société (comme les exports) ; autre société : 404.

Design inchangé : mêmes boutons, une ligne d'aide sous « Télécharger le dossier complet » (FR, EN, ES, AR) et une phrase « tout ou rien » dans l'aide de la confirmation groupée.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

Aucune migration, aucune nouvelle dépendance (zip de la bibliothèque standard).

## Tests exécutés

- Backend : ruff, format, makemigrations --check ; `tests/test_archive_confirmation.py` (7 tests : T77 tout ou rien, complément, refus ; T84 contenu, empreintes, pas de doublon d'export, brouillon, isolation, noms de fichiers). Suite complète : 351 passés ; `test_ocr_unavailable_fails_recoverably_and_manual_entry_still_works` échoue aussi sur `main` sur cette machine (outillage OCR local), à confirmer par la CI.
- Frontend : typecheck, vitest (77 passés, dont l'envoi unique de la confirmation groupée et le téléchargement de l'archive), build.

## Limites

- L'archive est construite à la demande (mémoire jusqu'à 32 Mo puis fichier temporaire) ; elle n'est pas conservée côté serveur, seul son téléchargement et son empreinte sont journalisés.
- Une pièce reprise dans une nouvelle révision figure dans chaque dossier `revision-N/` (mêmes octets).
- Libellés de l'archive en français, regroupés dans `apps/cases/archive.py` pour une autre langue de sortie.
- « Marquer comme exporté » reste désactivé ; le fichier pour SYDONIA attend la confirmation de son format.

## Prochaine étape

Format SYDONIA quand il sera confirmé avec la Douane ; ensuite « Marquer comme exporté » et l'archivage du dossier (état « Archivé »).
