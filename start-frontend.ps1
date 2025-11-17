# Démarrer seulement le frontend Electron (le backend doit déjà tourner)

Write-Host "Demarrage du frontend Electron..." -ForegroundColor Cyan
Set-Location (Join-Path $PSScriptRoot "frontend")
$env:PATH = "C:\Program Files\nodejs;" + $env:PATH

# Vérifier que le backend est disponible
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "Backend detecte - demarrage de l'interface..." -ForegroundColor Green
} catch {
    Write-Host "ATTENTION: Backend non disponible sur http://127.0.0.1:8000" -ForegroundColor Yellow
    Write-Host "Veuillez d'abord demarrer le backend avec start-backend.ps1" -ForegroundColor Yellow
    Read-Host "Appuyez sur Entree pour continuer quand meme ou Ctrl+C pour annuler"
}

npm run electron:dev
