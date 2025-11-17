# ==========================================
# DECLADO-IA - Script de lancement développement
# ==========================================

Write-Host "`n[DECLADO-IA] Lancement en mode developpement`n" -ForegroundColor Cyan

# Vérifier que tout est installé
if (!(Test-Path "backend/venv")) {
    Write-Host "[ERREUR] Environnement Python non trouve. Executez d'abord:" -ForegroundColor Red
    Write-Host "   .\scripts\setup.ps1`n" -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path "frontend/node_modules")) {
    Write-Host "[ERREUR] node_modules non trouve. Executez d'abord:" -ForegroundColor Red
    Write-Host "   .\scripts\setup.ps1`n" -ForegroundColor Yellow
    exit 1
}

# Lancer le backend
Write-Host "[BACKEND] Lancement du backend..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    cd backend
    .\venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
}

# Attendre que le backend soit prêt
Write-Host "[INFO] Attente du backend..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# Vérifier si le backend répond
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health/ping" -UseBasicParsing -TimeoutSec 10
    Write-Host "[OK] Backend pret !" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Backend ne repond pas encore, mais on continue..." -ForegroundColor Yellow
}

# Lancer le frontend
Write-Host "`n[FRONTEND] Lancement du frontend Electron..." -ForegroundColor Yellow
cd frontend
npm run electron:dev

# Cleanup au cas où
Write-Host "`n[CLEANUP] Arret des processus..." -ForegroundColor Cyan
Stop-Job $backendJob
Remove-Job $backendJob
