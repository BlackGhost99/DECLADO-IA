# Nettoyer et redémarrer DECLADO-IA

Write-Host "Nettoyage..." -ForegroundColor Cyan

# Tuer processus sur port 5173
netstat -ano | findstr ":5173" | findstr "LISTENING" | ForEach-Object {
    if ($_ -match '\s+(\d+)\s*$') {
        taskkill /F /PID $matches[1] 2>$null
    }
}

# Tuer processus sur port 8000
netstat -ano | findstr ":8000" | findstr "LISTENING" | ForEach-Object {
    if ($_ -match '\s+(\d+)\s*$') {
        taskkill /F /PID $matches[1] 2>$null
    }
}

Start-Sleep -Seconds 2

Write-Host "Demarrage backend dans une nouvelle fenetre..." -ForegroundColor Green
$backendScript = Join-Path $PSScriptRoot "backend\start-backend.ps1"
Start-Process powershell -ArgumentList "-NoExit -Command & '$backendScript'"

Start-Sleep -Seconds 8

Write-Host "Demarrage frontend..." -ForegroundColor Green
Set-Location (Join-Path $PSScriptRoot "frontend")
$env:PATH = "C:\Program Files\nodejs;" + $env:PATH

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  DECLADO-IA - Interface de demarrage" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Backend: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
Write-Host "  NE FERMEZ PAS cette fenetre pendant l'execution!" -ForegroundColor Red
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

npm run electron:dev
