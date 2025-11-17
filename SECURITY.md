# Sécurité & Chiffrement Local — DECLADO-IA

## Vue d'ensemble

DECLADO-IA protège les données sensibles en local via plusieurs mécanismes de sécurité :

- **DB chiffrée (SQLCipher)** : stockage de toutes données persistantes dans une base SQLite chiffrée (AES-256).
- **Gestion de clés sécurisée** : dérivation PBKDF2 + stockage DPAPI sous Windows ; salage et hachage robustes.
- **Journaux d'audit immuables** : logs HMAC-signés en mode append-only avec chaînage ; détection de tampering.
- **Scan antivirus optionnel** : détection automatique de Windows Defender ou ClamAV ; refus de fichiers infectés avant traitement OCR.
- **Vérification de signatures** : validation d'intégrité des modèles ML et référentiels via HMAC au démarrage.

## 1. Base de données chiffrée

### Architecture

- **Moteur** : SQLCipher (SQLite + AES-256-CBC).
- **Clé DB** : dérivée via PBKDF2-HMAC-SHA256 avec 200 000 itérations.
- **Passphrase source** : variable `DB_PASSPHRASE` (recommandé) ou `SECRET_KEY` (fallback).
- **Salage** : 16 octets aléatoires persistés dans `DB_SALT_PATH` (~/.../db_key.salt).

### Keystore DPAPI (Windows)

- Sur Windows, la clé dérivée de 32 octets est **chiffrée via DPAPI** (CryptProtectData) et stockée dans `DB_KEYSTORE_PATH` (~/.../db_key.bin).
- Seul l'utilisateur courant du système peut déchiffrer ce fichier.
- Au démarrage de l'application, la clé est rechargée depuis le keystore via CryptUnprotectData.

### Plateformes non-Windows

- La clé est dérivée à la volée depuis passphrase + salt (non persistée).
- **⚠ Avertissement** : si `DB_PASSPHRASE` n'est pas définie, la clé est dérivée de `SECRET_KEY`—moins sécurisé.

### Configuration

Ajouter dans `.env` :

```
DB_PASSPHRASE=your_strong_passphrase_here
DB_KEYSTORE_PATH=C:/Users/<User>/AppData/Roaming/DECLADO-IA/db_key.bin
DB_SALT_PATH=C:/Users/<User>/AppData/Roaming/DECLADO-IA/db_key.salt
DB_PBKDF2_ITERATIONS=200000
```

### Vérification

Au démarrage, un log apparaîtra :
```
INFO:app.db.database:SQLCipher version: 4.X.X
```

Si vous tentez de lire le fichier `./data/declado.db` avec `sqlite3`, vous obtiendrez "file is encrypted or not a database". ✅

## 2. Journaux d'audit HMAC-signés

### Principe

- Chaque entrée de log contient `{ ts, level, name, msg, model_version, user, prev_hmac, hmac }`.
- `hmac = HMAC-SHA256(key, prev_hmac || ts || level || name || msg || model_version || user)`.
- Le log forme ainsi une **chaîne immuable** : modifier un seul caractère brise le chaînage.

### Activation

Le handler `HMACFileHandler` est activé au démarrage dans `main.py` :

```python
from app.security.hmac_logger import configure_hmac_logging
configure_hmac_logging()
```

Logs append-only : `./logs/declado-audit.log` (JSONL).

### Vérification d'intégrité

```bash
cd backend
.venv/Scripts/python verify_logs.py ./logs/declado-audit.log
```

Sortie attendue :
```
✅ Log chain verified: ./logs/declado-audit.log
```

Si un log a été modifié, le script retourne un exit code 1 avec message d'erreur.

### Configuration

Clé HMAC :
```
LOG_HMAC_KEY=your_separate_hmac_key_here
```

Si non définie, `SECRET_KEY` est utilisée.

## 3. Scan antivirus pré-import

### Détection automatique

- **Windows Defender** : `MpCmdRun.exe` (chemin auto-détecté ou via `AV_DEFENDER_PATH`).
- **ClamAV** : `clamscan` (auto-détecté ou via `AV_CLAMSCAN_PATH`).

### Activation

Par défaut activé (`AV_SCAN_ENABLED=true`). Pour désactiver :

```
AV_SCAN_ENABLED=false
```

### Comportement

Lors de l'upload d'un fichier via `/api/ocr/process` :

1. Le fichier est écrit dans un répertoire temporaire.
2. **AV scan** exécuté (timeout 120s).
3. Si menace détectée : `HTTP 400` avec message `"Antivirus: fichier refusé (…)"`.
4. Si propre ou si AV indisponible : traitement continue.

### Logs

Logs backend :
```
WARNING:app.security.antivirus:Defender scan failed: ...
INFO:app.api.ocr:Uploaded file scan: Windows Defender: clean
```

## 4. Vérification de signatures (modèles & référentiels)

### Principe

- Chaque dossier/fichier sensible (ex. `./ml/models/`, `./config/`) peut être accompagné d'un fichier `.sig` (JSON).
- Format :
  ```json
  {
    "algo": "HMAC-SHA256",
    "digest": "sha256(files_concat)",
    "hmac": "hmac(key, digest)"
  }
  ```
- Au démarrage, `lifespan()` vérifie les `.sig` présents pour les chemins définis dans `SIGNED_REPOS`.

### Configuration

```
SIGNED_REPOS=["./ml/models", "./config"]
LOG_HMAC_KEY=shared_signing_key
```

Si un fichier `.sig` existe et est invalide, l'application **refuse de démarrer** (RuntimeError).

### Génération de signatures

Utilisez le script `sign_repo.py` (à créer) ou un outil externe pour générer les `.sig`.

Exemple :
```python
import json
from app.security.signatures import compute_dir_digest
import hmac, hashlib

digest = compute_dir_digest(Path("./ml/models"))
key = "your_key".encode()
mac = hmac.new(key, digest.encode(), hashlib.sha256).hexdigest()
sig = {"algo": "HMAC-SHA256", "digest": digest, "hmac": mac}
Path("./ml/models/.sig").write_text(json.dumps(sig))
```

## 5. Backup & Restauration

### Export DB chiffrée

```bash
cd backend
.venv/Scripts/python backup_db.py export backup_20251116.db
```

Le fichier `backup_20251116.db` est une **copie chiffrée** : illisible sans la clé.

### Restauration

```bash
.venv/Scripts/python backup_db.py restore backup_20251116.db --db ./data/declado.db
```

⚠ **Importante** : la clé/passphrase doit être la même que lors de l'export.

### Stockage sécurisé

- Ne jamais commiter `db_key.bin`, `db_key.salt`, ni le fichier DB dans Git.
- Backups : stocker hors-ligne ou dans un coffre chiffré (ex. Azure Key Vault, AWS KMS, Bitwarden).

## 6. Critères d'acceptation

### ✅ DB non lisible sans clé

```bash
sqlite3 ./data/declado.db
# Error: file is encrypted or not a database
```

### ✅ Logs vérifiables

```bash
.venv/Scripts/python verify_logs.py ./logs/declado-audit.log
# ✅ Log chain verified
```

Modifier manuellement une ligne dans `declado-audit.log`, puis :
```bash
.venv/Scripts/python verify_logs.py ./logs/declado-audit.log
# ❌ Log chain INVALID
```

### ✅ Scan antivirus

- Upload d'un fichier de test EICAR : réponse HTTP 400 `"Antivirus: fichier refusé"`.
- Upload d'un PDF normal : scan OK, traitement continue.

### ✅ Signatures modèle

- Créer un `.sig` invalide dans `./ml/models/` → app refuse de démarrer.
- Supprimer le `.sig` → app démarre (signature facultative).

## 7. Résumé des fichiers

| Fichier | Rôle |
|---------|------|
| `app/security/key_manager.py` | Dérivation PBKDF2 + DPAPI ; génération/chargement clé DB |
| `app/security/hmac_logger.py` | Handler logging HMAC-signé ; `verify_log_chain()` |
| `app/security/antivirus.py` | Détection Defender/ClamAV ; `scan_file()` |
| `app/security/signatures.py` | Vérification HMAC signatures de dossiers/fichiers |
| `app/core/config.py` | Settings : `DB_PASSPHRASE`, `AV_SCAN_ENABLED`, `SIGNED_REPOS`, etc. |
| `backup_db.py` | Script export/restore DB chiffrée |
| `verify_logs.py` | Vérifier intégrité chaîne HMAC logs |

## 8. Bonnes pratiques

1. **Passphrase forte** : 20+ caractères, alphanumérique + symboles.
2. **Ne jamais partager `db_key.bin` ou `.salt`** : spécifique à l'utilisateur/machine Windows.
3. **Rotate `SECRET_KEY` et `LOG_HMAC_KEY`** régulièrement (minimum 1x/an).
4. **Auditer les logs** : surveiller les événements critiques (échecs de connexion, erreurs OCR répétées).
5. **Tester les backups** : restaurer régulièrement pour valider l'accessibilité.
6. **Signer les modèles** : avant déploiement en production, générer les `.sig` pour `ml/models`.

## 9. Troubleshooting

### "cipher_version vide" ou "file is encrypted"

- Vérifier que le driver `pysqlcipher3` est installé (voir `requirements.txt`).
- Windows : compiler SQLCipher ou utiliser un wheel précompilé.
- Si migration depuis SQLite non chiffré, exporter les données et ré-importer dans une DB chiffrée.

### "CryptUnprotectData failed"

- Keystore `db_key.bin` créé par un autre utilisateur Windows → impossible de déchiffrer.
- Solution : supprimer `db_key.bin` et `db_key.salt` ; redémarrer l'app pour régénérer avec le compte actuel.

### Logs HMAC invalides

- Clé modifiée entre écriture et vérification.
- Log édité manuellement.
- Corruption du fichier.

→ Impossible de "réparer" : archiver le log corrompu et démarrer un nouveau log propre.

---

**Contact** : Pour toute question sur la sécurité de DECLADO-IA, référez-vous à la documentation technique ou contactez l'équipe core.
