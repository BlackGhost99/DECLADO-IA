# DECLADO-IA - Démarrage manuel

## Procédure en 2 étapes

### Étape 1: Démarrer le backend

1. Ouvrez une fenêtre PowerShell
2. Naviguez vers le dossier backend:
   ```powershell
   cd C:\Users\BlackGhost\Desktop\DECLADO-IA\backend
   ```
3. Lancez le backend:
   ```powershell
   .\start-backend.ps1
   ```
4. **Attendez** de voir le message `INFO: Application startup complete.`
5. **GARDEZ cette fenêtre ouverte!**

Le backend sera disponible sur http://127.0.0.1:8000

### Étape 2: Démarrer le frontend

1. Ouvrez une **NOUVELLE** fenêtre PowerShell (ne fermez pas celle du backend!)
2. Naviguez vers le dossier frontend:
   ```powershell
   cd C:\Users\BlackGhost\Desktop\DECLADO-IA\frontend
   ```
3. Ajoutez Node au PATH (temporaire):
   ```powershell
   $env:PATH = "C:\Program Files\nodejs;" + $env:PATH
   ```
4. Lancez l'interface Electron:
   ```powershell
   npm run electron:dev
   ```
5. **Attendez** que la fenêtre Electron s'ouvre (~10-15 secondes)

L'application s'ouvrira automatiquement dans une fenêtre Electron.

## Vérification

- Backend: http://127.0.0.1:8000/api/health (doit retourner du JSON)
- Frontend Vite: http://localhost:5173 (dans le navigateur)
- Electron: Se lance automatiquement

## Arrêt

1. Fermez la fenêtre Electron
2. Dans la fenêtre PowerShell du frontend: Ctrl+C
3. Dans la fenêtre PowerShell du backend: Ctrl+C

## Dépannage

**"Backend timeout"**: Le backend n'est pas démarré ou n'a pas fini de démarrer. Attendez 5-10 secondes de plus.

**"Port 5173 already in use"**: Un ancien processus Vite tourne encore. Tuez-le:
```powershell
Get-Process | Where-Object {$_.ProcessName -like "*node*"} | Stop-Process -Force
```

**"Port 8000 already in use"**: Un ancien backend tourne. Tuez-le:
```powershell
netstat -ano | findstr :8000
# Notez le PID et:
taskkill /F /PID <PID>
```
