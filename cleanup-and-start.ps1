# Script pour nettoyer et redémarrer DECLADO-IA proprement

Write-Host "🧹 Nettoyage des processus existants..." -ForegroundColor Cyan

# Tuer tous les processus Python/Node sur les ports 5173 et 8000
$portsToClean = @(5173, 8000)
foreach ($port in $portsToClean) {
    $connections = netstat -ano | findstr ":$port" | findstr "LISTENING"
    if ($connections) {
        $connections | ForEach-Object {
            if ($_ -match '\s+(\d+)\s*$') {
                $processId = $matches[1]
                try {
                    Write-Host "  Arrêt du processus $processId sur port $port" -ForegroundColor Yellow
                    taskkill /F /PID $processId 2>&1 | Out-Null
                } catch {
                    # Ignore errors
                }
            }
        }
    }
}

Write-Host "✅ Nettoyage terminé" -ForegroundColor Green
Write-Host ""

# Attendre que les ports se libèrent
Start-Sleep -Seconds 2

# Démarrer le backend
Write-Host "🚀 Démarrage du backend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList '-NoExit','-Command',"cd 'C:\Users\BlackGhost\Desktop\DECLADO-IA\backend'; .\start-backend.ps1"

# Attendre que le backend démarre
Start-Sleep -Seconds 5

# Tester le backend
Write-Host "🔍 Test de connexion au backend..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Backend opérationnel!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "⚠️  Backend non disponible, réessayez dans quelques secondes" -ForegroundColor Yellow
    Write-Host ""
}

# Démarrer le frontend
Write-Host "🚀 Démarrage du frontend..." -ForegroundColor Cyan
Set-Location C:\Users\BlackGhost\Desktop\DECLADO-IA\frontend
$env:PATH = 'C:\Program Files\nodejs;' + $env:PATH
npm run electron:dev
