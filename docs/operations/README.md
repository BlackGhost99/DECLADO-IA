# Exploitation

Lot 0 : environnement de développement uniquement (voir README racine).

À compléter avant la recette (lot 6) : hébergement, sauvegarde base + stockage, procédure de restauration testée
(objectifs proposés RPO 24 h, RTO 4 h), rotation des secrets, conservation et effacement.

Règles déjà en place :
- secrets uniquement par variables d'environnement (`backend/.env.example`), `.env` ignoré par Git ;
- `DJANGO_DEBUG=false` impose `DJANGO_SECRET_KEY` et active cookies Secure + HSTS ;
- chaque réponse porte `X-Request-ID`, repris dans les journaux techniques ;
- le journal d'audit est en ajout seul, y compris en base.
- pièces des dossiers hors racine web, dans `PRIVATE_STORAGE_ROOT` (volume `private` sous Docker) : la sauvegarde doit
  couvrir ensemble la base et ce répertoire ; les octets ne sortent que par lien temporaire contrôlé (ADR-009).
- extraction (lot 3) : un worker Celery avec beat (`-B`, ou un processus `celery beat` distinct) est nécessaire ;
  Tesseract est installé dans l'image backend. Un travail interrompu est repris après expiration de son bail (30 min).
  Aucun fournisseur d'IA n'est raccordé (`AI_PROVIDER=disabled`) : aucune pièce ne quitte le serveur.
