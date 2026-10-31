# ClairTransit P0 — Défense documentaire à deux niveaux

## Architecture retenue

**Méthode 1 : antivirus reconnu** : ClamAV auto-hébergé et mis à jour par FreshClam.
**Méthode 2 : sécurité applicative ClairTransit** : authentification, société active,
permissions, limites d'upload, reconnaissance MIME basée sur les octets, vérification
de structure, stockage privé et liens temporaires.

Tous les uploads externes passent par le service commun `documents.store_upload`.

```text
Utilisateur autorisé → quarantaine privée 0600 → ClamAV INSTREAM
     ├── FOUND            → 422, fichier détruit, aucun Document exploitable
     ├── panne/timeout    → 503, fichier détruit, aucun Document exploitable
     └── OK               → MIME/extension/structure/limites
                                ├── refus → 422/413, fichier détruit
                                └── OK → promotion atomique → stockage privé → OCR/IA
```

Ni le navigateur, ni OCR, ni IA ne peuvent lire un fichier bloqué en quarantaine ;
seuls les fichiers acceptés obtiennent une clé de stockage documentaire.
Le client `clamd` utilise INSTREAM et n'envoie pas de chemins arbitraires.
Le port 3310 ne doit pas être accessible depuis Internet : protocole TCP sans
authentification ni TLS natifs. Aucun interrupteur de contournement n'est prévu.

## Paramétrage et démarrage

`docker compose -f infra/compose.yaml up --build`

Le service `clamav` n'expose pas de port hôte. Les signatures sont conservées
dans `clamdb`. Pendant leur téléchargement et le démarrage du scanner, les
uploads sont refusés (fail closed). Les variables `CLAMAV_HOST`,
`CLAMAV_PORT`, `CLAMAV_CONNECT_TIMEOUT` et `CLAMAV_SCAN_TIMEOUT`
sont configurées pour backend/worker.

Hors Docker, fournir un clamd accessible en réseau privé et exécuter
`python manage.py seed_document_types` après `migrate`. Vérifier que
`StreamMaxLength` et `MaxFileSize` supportent la limite
`DOCUMENT_MAX_BYTES` (50 Mio par défaut). Surveiller la mise à jour des
signatures, le taux d'erreurs de scan et les capacités mémoire/CPU.

## Taxonomie définitive V1

`regulations.DocumentType` reste l'unique catalogue ; `taxonomy.py`
déclare les codes stables dans sept familles. `seed_document_types` est
idempotente et crée les types SANS publier aucune obligation légale.

`DocumentClassification` (déjà livré par la PR #15) continue à conserver
les confirmations **humaines** et leur historique. Il n'existe pas de second
champ parallèle pour la classification. Une facture de fret ne devient
jamais une facture commerciale par simple intitulé `invoice`.
Les types de transport génériques ne prouvent pas qu'il s'agit d'un B/L ou
d'une LTA. La checklist réglementaire reste indicative et soumise aux
règles CEMAC/nationales datées, vérifiées et publiées.

## Critères de validation P0

- ClamAV détecte la signature inoffensive EICAR, refus 422, zéro fichier promu.
- ClamAV en panne ou résultat inattendu : refus 503, zéro fichier promu.
- Fichier sain : conservation exacte des octets, SHA-256 et stockage 0600.
- Contenu PNG avec nom/extension PDF : refus MIME applicatif.
- Une société ne peut consulter ou télécharger les documents d'une autre.
- Tests backend, migrations, vérification Ruff, tests frontend : CI réussie.
- En production : ClamAV relié au backend, signatures à jour, volumes
  persistants, limitation réseau et contrôle de restauration sauvegarde.

### Preuve sur le poste (Windows)

- `python manage.py verifier_antivirus` : version et date des signatures de
  clamd, essai EICAR (reconstitué en mémoire, jamais écrit sur le disque, pour
  que Windows Defender ne le supprime pas) qui doit être refusé, contenu sain
  qui doit être accepté. Code de sortie non nul sinon.
- Le script `scripts/windows/demarrer-clairtransit.ps1` lance ce contrôle à
  chaque démarrage (section « Contrôle de l'antivirus »).
- `-ImporterTarif` : le fichier passe par ClamAV
  (`verifier_antivirus --seulement-fichiers --fichier ...`) avant toute
  lecture ; auparavant les commandes d'import lisaient le fichier directement.

### Données déjà présentes

Les documents stockés avant activation de ClamAV ne comportent pas de
preuve antivirus historique. Ils doivent être analysés avant toute réutilisation
opérationnelle. Ne jamais les considérer rétrospectivement comme sains.

Cette livraison couvre P0 documentaire ; elle ne certifie pas toute la
sécurité plateforme (MFA, sauvegardes restaurables, contrôle des secrets,
protection des fournisseurs IA), qui reste à valider séparément.
