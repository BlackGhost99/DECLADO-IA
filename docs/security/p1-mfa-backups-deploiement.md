# ClairTransit — mise en production des protections P1

## Authentification multifacteur

Cette livraison ajoute une MFA **TOTP** : authentificateur RFC 6238,
secret chiffré au repos (Fernet), connexion en deux étapes, codes de récupération
individuellement utilisables une seule fois, blocage de réutilisation d'un code
TOTP, limitation des essais via Redis et journalisation des activations/connexions.

- En développement, `DJANGO_DEBUG=true` laisse `MFA_ENFORCE=false`.
- En production, `DJANGO_DEBUG=false` active la MFA **par défaut**, et
  `MFA_ENCRYPTION_KEY` est obligatoire : sans clé, le serveur refuse le
  démarrage. Éviter d'utiliser une clé dérivée de `DJANGO_SECRET_KEY`.
- Générer une clé Fernet indépendante :
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
  Conserver dans un gestionnaire de secrets ; ne jamais la publier dans Git,
  une image Docker ou un rapport.
- Fournir `CACHE_URL` vers Redis privé partagé par les instances,
  ex. `redis://redis:6379/1`; panne Redis => tentatives de connexion bloquées.
- Tous les employés sont invités à activer la MFA à leur première
  connexion. Les comptes déjà associés à un authentificateur ne reçoivent
  pas de session utilisable avant la validation du second facteur.
- Les dix codes de récupération ne sont affichés qu'une fois ; les hachages
  de vérification sont stockés en base. Un code consommé ne fonctionne plus.
- Sauvegarder la clé Fernet dans un coffre indépendant des sauvegardes.
  Ne **pas** la changer sans procédure de ré-enchiffrement des secrets ;
  elle est nécessaire après une restauration.
- Prévoir une procédure d'assistance administrateur avec vérification
  d'identité hors bande si un utilisateur perd appareil **et** codes.

## API, navigateur et secrets

- Session serveur, CSRF sur le login et le second facteur ; cookies
  HttpOnly, Secure et HSTS en production.
- En production, requêtes API limitées dans DRF et mots de passe/MFA
  limités via Redis ; sessions avec accès métier bloquées tant que la MFA
  n'est pas validée.
- Les réponses d'authentification sont non mises en cache.
- Les fonctions `AI_PROVIDER=disabled` ne contactent aucun fournisseur
  IA externe par défaut. Avant toute activation, prévoir des contrats
  de sous-traitance, une politique de données et un cloisonnement des appels.
- GitHub Dependabot propose des mises à jour de dépendances ;
  chaque proposition doit rester soumise aux tests et à revue.

## Sauvegarde / restauration

Les scripts sous `infra/backup/` créent des sauvegardes chiffrées
PostgreSQL + pièces privées, avec un essai de restauration réelle validé
en CI sur un environnement isolé.

Pour la production il reste à **configurer effectivement** :
1. Le fournisseur de stockage **hors site** et ses identifiants restreints
   (`RESTIC_REPOSITORY` et credentials du fournisseur).
2. Le secret `RESTIC_PASSWORD_FILE` durable et indépendant, avec une
   seconde copie hors site du secret.
3. Les identifiants de la base destinés au `pg_dump` et le montage des
   pièces en lecture seule.
4. Un planificateur quotidien, une alerte d'échec, une rétention vérifiée
   et des exercices de restauration sur une infrastructure isolée.
5. La conformité de sauvegarde au RGPD et aux obligations applicables,
   notamment les durées de conservation et l'effacement.

Le profil Compose `backup` est uniquement un **mode d'essai local chiffré**.
Il ne constitue **pas** une sauvegarde anti-catastrophe.
Aucune donnée commerciale réelle ne doit être placée dans cette
configuration de développement.

La CI a testé le chiffrement, la sauvegarde, la vérification d'intégrité
et la restauration dans une base de test. Elle ne démontre ni
la disponibilité d'un stockage distant ni la restauration du serveur
de production : ces vérifications nécessitent le déploiement réel.
