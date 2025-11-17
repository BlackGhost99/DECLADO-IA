# Guide: Configuration de Windows Defender pour DECLADO-IA

## 🔍 Problème: Faux positifs de Windows Defender

Windows Defender peut parfois bloquer des fichiers légitimes en tant que menaces. Cela se produit notamment lors du développement ou du test de fichiers.

## ✅ Solutions pour Réactiver le Scan AV

### **Option 1: Exclure le répertoire de test (RECOMMANDÉE)**

**Étapes:**

1. **Ouvrir PowerShell en tant qu'Administrateur**
   ```powershell
   # Run the exclusion script as Administrator
   cd c:\Users\BlackGhost\Desktop\DECLADO-IA\backend
   powershell -ExecutionPolicy Bypass -File configure-defender-exclusion.ps1
   ```

2. **Vérifier les exclusions**
   ```powershell
   Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
   ```

3. **Ajouter manuellement (si le script échoue)**
   ```powershell
   Add-MpPreference -ExclusionPath "C:\Users\BlackGhost\Desktop\DECLADO-IA\test_files"
   ```

### **Option 2: Ajouter une exclusion via l'interface Defender**

1. Ouvrir "Virus & threat protection"
2. Cliquer sur "Manage settings"
3. Descendre à "Exclusions"
4. Cliquer "Add exclusions"
5. Sélectionner "Folder"
6. Choisir: `C:\Users\BlackGhost\Desktop\DECLADO-IA\test_files`

### **Option 3: Exclure des fichiers spécifiques**

```powershell
# Exclure un fichier spécifique
Add-MpPreference -ExclusionPath "C:\Users\BlackGhost\Desktop\DECLADO-IA\test_files\ddd.png"

# Exclure par extension
Add-MpPreference -ExclusionExtension "png"
```

## 🔧 Configuration dans DECLADO-IA

### Fichier: `.env`

```
# Enable AV scan in development with excluded paths
AV_SCAN_ENABLED=True
```

### Réactiver progressivement

1. **Vérifier que le scan est activé:**
   ```bash
   # Voir la config actuelle
   grep AV_SCAN_ENABLED .env
   # Output: AV_SCAN_ENABLED=True
   ```

2. **Tester avec un fichier "sain":**
   - Placer le fichier dans `c:\Users\BlackGhost\Desktop\DECLADO-IA\test_files\`
   - Uploader via l'interface
   - Vérifier les logs: `AV scan result: is_clean=True`

3. **Si faux positif persiste:**
   - Ajouter le fichier à l'exclusion Defender
   - Ou désactiver le scan temporairement: `AV_SCAN_ENABLED=False`

## 📋 Statut du Scan AV

Pour vérifier le statut:

```powershell
# Vérifier si Defender est actif
Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled

# Voir les exclusions actives
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath

# Voir les extensions exclues
Get-MpPreference | Select-Object -ExpandProperty ExclusionExtension
```

## 🛡️ Recommandations Sécurité

- **Développement:** `AV_SCAN_ENABLED=True` avec exclusions pour fichiers de test
- **Production:** `AV_SCAN_ENABLED=True` sans exclusions larges
- **Alternative:** Utiliser ClamAV à la place de Defender pour plus de contrôle
- **Monitoring:** Vérifier les logs d'audit pour les fichiers rejetés

## 🔗 Ressources

- [Windows Defender Exclusions](https://learn.microsoft.com/en-us/microsoft-365/security/defender-endpoint/configure-exclusions-microsoft-defender-antivirus)
- [PowerShell MpPreference](https://learn.microsoft.com/en-us/powershell/module/defender/set-mppreference)
- [ClamAV Integration](https://www.clamav.net/)
