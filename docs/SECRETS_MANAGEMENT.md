# ==========================================
# DECLADO-IA - Gestion des Secrets
# ==========================================

## ⚠️ IMPORTANT - Sécurité

**Ne JAMAIS committer les fichiers suivants :**
- `.env`
- `secrets.json`
- `*.key`
- `*.pem`
- `*.p12`
- `*.pfx`
- Tout fichier contenant des mots de passe ou clés

Ces fichiers sont déjà dans `.gitignore`.

## Configuration initiale

### 1. Backend (Python)

```bash
# Copier le template
cp .env.example .env

# Éditer avec vos valeurs réelles
notepad .env  # ou votre éditeur préféré

# Générer une clé secrète forte
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Secrets avancés (JSON)

```bash
# Copier le template
cp secrets.example.json secrets.json

# Éditer avec vos valeurs
notepad secrets.json
```

### 3. Génération de clés de chiffrement

Pour la base de données SQLite chiffrée :

```python
import os
import base64

# Générer une clé de 32 bytes
key = os.urandom(32)
key_b64 = base64.b64encode(key).decode('utf-8')
print(f"DATABASE_ENCRYPTION_KEY={key_b64}")
```

## Variables d'environnement critiques

### Clés à générer absolument

1. **SECRET_KEY** - Pour JWT et sessions
2. **DATABASE_ENCRYPTION_KEY** - Pour SQLCipher
3. **CODE_SIGNING_PASSWORD** - Pour signer les builds Windows

### Exemple de génération

```powershell
# PowerShell - Générer des clés fortes
[System.Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
```

## Certificat de signature Windows

Pour signer les builds Windows (IMPORTANT pour éviter les alertes de sécurité) :

### Obtention d'un certificat

1. **Certificat commercial** (recommandé pour production)
   - DigiCert, Sectigo, GlobalSign
   - Code Signing Certificate
   - ~300-500€/an

2. **Certificat auto-signé** (développement uniquement)
   ```powershell
   # Créer un certificat de test
   $cert = New-SelfSignedCertificate `
     -Subject "CN=DECLADO-IA Development" `
     -Type CodeSigningCert `
     -CertStoreLocation Cert:\CurrentUser\My `
     -NotAfter (Get-Date).AddYears(2)
   
   # Exporter en PFX
   $password = ConvertTo-SecureString -String "YourPassword" -Force -AsPlainText
   Export-PfxCertificate -Cert $cert -FilePath ".\certificates\declado-dev.pfx" -Password $password
   ```

### Configuration dans secrets.json

```json
{
  "code_signing": {
    "certificate_path": "C:\\DECLADO-IA\\certificates\\your-cert.pfx",
    "certificate_password": "YOUR_CERT_PASSWORD",
    "timestamp_url": "http://timestamp.digicert.com"
  }
}
```

## Stockage sécurisé

### Développement local

1. Fichiers `.env` et `secrets.json` **uniquement en local**
2. **Jamais** dans Git
3. Backup chiffré sur stockage externe sécurisé

### Production

1. Utiliser un gestionnaire de secrets :
   - **Windows** : Credential Manager, Azure Key Vault
   - **Entreprise** : HashiCorp Vault, AWS Secrets Manager
   
2. Variables d'environnement système sécurisées

3. Clés de chiffrement stockées en HSM (Hardware Security Module) si possible

## Rotation des secrets

**Recommandations :**
- Secrets JWT : tous les 3 mois
- Clés de chiffrement DB : tous les 6-12 mois
- Certificats de signature : renouveler avant expiration
- Mots de passe API : tous les 6 mois

## Checklist avant déploiement

- [ ] Toutes les valeurs `CHANGE_ME` ont été remplacées
- [ ] Clés générées aléatoirement (pas de valeurs par défaut)
- [ ] Certificat de signature valide configuré
- [ ] Fichiers secrets exclus de Git (`.gitignore` OK)
- [ ] Backup des secrets dans un coffre-fort sécurisé
- [ ] Documentation des secrets pour l'équipe (emplacements, pas valeurs)
- [ ] Tests de fonctionnement avec les vraies clés

## En cas de compromission

1. **Immédiatement** :
   - Révoquer les clés compromises
   - Générer de nouvelles clés
   - Changer tous les mots de passe
   
2. **Audit** :
   - Vérifier les logs d'accès
   - Identifier la source de la fuite
   
3. **Communication** :
   - Notifier l'équipe
   - Informer les clients si nécessaire

## Support

Pour toute question sur la sécurité : security@declado-ia.com
