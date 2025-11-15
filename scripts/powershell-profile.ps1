# ==========================================
# DECLADO-IA - PowerShell Profile Helper
# ==========================================
# Ce script ajoute Git au PATH automatiquement

# Ajouter Git au PATH si pas déjà présent
if ($env:Path -notlike "*Git\cmd*") {
    $env:Path += ";C:\Program Files\Git\cmd"
}

# Fonction helper pour DVC
function Invoke-DVC {
    python -m dvc @args
}
Set-Alias -Name dvc -Value Invoke-DVC

# Naviguer rapidement vers le projet
function goto-declado {
    Set-Location "C:\Users\BlackGhost\Desktop\DECLADO-IA"
}
Set-Alias -Name declado -Value goto-declado

# Activer l'environnement virtuel backend
function activate-backend {
    & "C:\Users\BlackGhost\Desktop\DECLADO-IA\backend\venv\Scripts\Activate.ps1"
}
Set-Alias -Name venv-backend -Value activate-backend

Write-Host "✅ DECLADO-IA helpers loaded!" -ForegroundColor Green
Write-Host "Aliases disponibles:" -ForegroundColor Cyan
Write-Host "  - declado        : Aller au dossier du projet" -ForegroundColor Yellow
Write-Host "  - venv-backend   : Activer l'environnement Python" -ForegroundColor Yellow
Write-Host "  - dvc            : Utiliser DVC" -ForegroundColor Yellow
