# Lot « Supervision » de la console ClairTransit (SUP-01 à SUP-06)

Demande du 2 novembre 2026 : voir depuis la page super admin si l'antivirus est actif et travaille, ses journaux, ce que lit l'IA et comment, pourquoi une pièce est refusée, et les erreurs rencontrées par les agents des sociétés — le plus de détails possible, sans informations confidentielles.

## Fonctionnalités terminées

- **Console > Supervision** (nouvelle entrée du menu de l'exploitant), période 24 h / 7 j / 30 j, six onglets :
  - **Antivirus** : état réel de ClamAV vérifié à l'ouverture (moteur, version et date des signatures, temps de réponse), mode « refus si pas de réponse saine », pièces saines / malveillantes / refusées faute de réponse, dernière analyse saine, dernier essai, journal. Bouton **Lancer l'essai** : EICAR reconstitué en mémoire (doit être refusé) puis contenu sain (doit être accepté), journalisé.
  - **Lecture des pièces** : moteurs disponibles (texte PDF, Excel, OCR Tesseract et ses langues, IA en ligne), lectures par type de pièce et par moteur, durée moyenne, lectures en échec (société, dossier, type, moteur, code et message).
  - **IA en ligne** : fournisseur, modèle, clé présente (jamais affichée), sociétés qui l'ont activée, demandes par état, jetons, coût estimé, temps de réponse, informations demandées / retenues / écartées, dernières demandes.
  - **Pièces refusées** : motif (antivirus, format, taille), société, agent, extension, type annoncé, taille, empreinte tronquée.
  - **Erreurs** : actions refusées (code, message vu par l'agent, adresse, méthode, code HTTP) et erreurs serveur (type seulement), travaux de fond en échec.
  - **Par société** : dossiers créés, pièces déposées, lectures réussies / en échec, pièces refusées, erreurs, envois à l'IA, dernière activité.
- **Journal de fonctionnement** (`apps.supervision.OperationalEvent`, append-only) : une requête refusée est annulée en base (ATOMIC_REQUESTS) ; les notes attendent donc la fin de la requête et sont écrites par `SupervisionMiddleware`, hors de sa transaction.
- Inclut la PR #57 (commande `verifier_antivirus`, contrôle au démarrage Windows, tarif du script analysé), restée ouverte : son essai EICAR est réutilisé par la console.

## Ce qui n'est jamais affiché

Contenu de pièce, nom de fichier, valeur lue, texte envoyé à l'IA, clé du service. Une erreur imprévue ne montre que son type (son texte pourrait contenir des données). Les lectures refusées (GET), 401, 403, 404, 405 et 429 ne sont pas notées.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `tests/test_supervision.py` : T90 (accès exploitant seul, état de ClamAV, ClamAV arrêté), T91 (pièces refusées journalisées sans nom de fichier), T92 (action refusée, erreur serveur sans son texte), T93 (essai EICAR réussi puis en échec).
- `frontend/tests/Supervision.test.tsx` : état, essai, pièces refusées, lectures en échec, période ; antivirus arrêté.

## Limites

- Les pièces refusées avant ce lot ne sont pas dans le journal (elles n'étaient que dans les journaux techniques du serveur).
- Les journaux internes de ClamAV (clamd.log) ne sont pas lus : la console montre ce que l'application a vu de ClamAV.
- Pas d'alerte e-mail ni de notification : la page se consulte.
- Le journal de fonctionnement n'a pas encore de durée de conservation ni de purge.

## Prochaine étape

Alerte visible dans la console quand ClamAV ne répond pas ou qu'un essai échoue ; durée de conservation du journal.

## Suite : OCR installé par le script Windows (2 novembre 2026)

La supervision montrait « OCR indisponible : Tesseract absent de ce serveur » : le script de démarrage n'installait pas Tesseract. Il le fait maintenant, dans l'étape « Lecture des scans (OCR Tesseract) » :

- un Tesseract déjà présent sur le PC (Program Files, profil utilisateur, PATH) est réutilisé ;
- sinon, l'installateur officiel UB Mannheim 5.5.0.20241111 est téléchargé, **analysé par ClamAV (clamscan) avant d'être ouvert**, puis installé sans question dans `outils\tesseract` (Windows peut demander une autorisation) ;
- les modèles de langue `eng`, `fra`, `spa`, `ara` et `osd` (tessdata_fast 4.1.0) sont téléchargés dans `outils\tessdata` et vérifiés par empreinte SHA-256 ;
- `TESSDATA_PREFIX` et le `PATH` du processus pointent vers eux : l'API lancée par le script les hérite ;
- en cas d'échec, l'application démarre quand même et l'avertissement l'indique.

Limite : l'installateur UB Mannheim n'est pas vérifié par une empreinte figée (impossible à relever depuis l'environnement de développement) ; il est analysé par ClamAV et son empreinte est affichée. Le script n'est pas mis à jour par `-MettreAJour` : il faut retélécharger `scripts/windows/demarrer-clairtransit.ps1`.
