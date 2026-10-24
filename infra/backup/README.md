# Sauvegardes ClairTransit — base + documents

Restic fournit le chiffrement authentifié du référentiel et la déduplication.
Le script `backup.sh` sauvegarde **dans le même snapshot Restic** un `pg_dump -Fc`
et le stockage privé, avant d'appliquer la rétention 7 jours / 4 semaines / 6 mois.
La version restaurée contient à la fois les métadonnées et les pièces.

## Production
- Fournir `RESTIC_REPOSITORY=s3:...` ou un autre référentiel distant indépendant
  du serveur ; fournir `RESTIC_PASSWORD_FILE` par un secret hors dépôt.
- Fournir `PGHOST`, `PGUSER`, `PGDATABASE` et `PGPASSFILE` via secrets ;
  monter `PRIVATE_STORAGE_ROOT` en lecture seule.
- Exécuter `backup.sh` automatiquement chaque jour via l'orchestrateur ;
  alerter sur tout code de sortie non nul.
- Activer rétention/immuabilité côté stockage distant (object lock si disponible),
  restriction réseau, sauvegarde de la clé et séparation des droits.
- Tester `restore-drill.sh` régulièrement **sur une instance isolée** avec
  `BACKUP_DRILL_RESTORE_DATABASE=true`. Jamais sur la base de production.
- Le test d'archive sans base isolée vérifie l'intégrité mais ne prouve pas
  qu'une restauration complète du service fonctionnerait.

## Développement / CI
`BACKUP_ALLOW_LOCAL=true` autorise un dépôt Restic local à des fins de test
uniquement. Aucun mot de passe, fournisseur de stockage ni clé de sauvegarde
réel n'est enregistré dans GitHub.

## Conditions de mise en production
La présence des scripts ne signifie pas qu'un fournisseur de stockage distant
est configuré, que des sauvegardes ont été exécutées ou qu'une restauration
production a été démontrée. Ces points nécessitent les secrets et
l'infrastructure de l'exploitant.
