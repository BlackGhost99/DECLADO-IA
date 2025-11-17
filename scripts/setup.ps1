# ==========================================
# DECLADO-IA - Setup et Installation Automatique
# ==========================================

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "[DECLADO-IA] Installation Automatique" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

$ErrorActionPreference = "Continue"

# Fonction pour vérifier une commande
function Test-Command {
    param($Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

# 1. Vérifier Python (système)
Write-Host "[1/8] Verification de Python (systeme)..." -ForegroundColor Yellow
if (Test-Command python) {
    $pythonVersion = python --version
    Write-Host "[INFO] System: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "[ERREUR] Python non trouve. Installation..." -ForegroundColor Red
    winget install Python.Python.3.11 -e
    Write-Host "[WARN] Veuillez redemarrer PowerShell apres l'installation de Python" -ForegroundColor Yellow
    exit
}

# 2. Vérifier Node.js
Write-Host "`n[2/8] Verification de Node.js..." -ForegroundColor Yellow
if (Test-Command node) {
    $nodeVersion = node --version
    Write-Host "[OK] Node.js $nodeVersion installe" -ForegroundColor Green
} else {
    Write-Host "[ERREUR] Node.js non trouve. Installation..." -ForegroundColor Red
    winget install OpenJS.NodeJS.LTS -e
    # Rafraichir PATH pour la session courante et tenter chemins connus
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path','Machine')
    $userPath = [System.Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = $machinePath + ';' + $userPath
    $nodeDirs = @(
        "C:\\Program Files\\nodejs",
        "$env:LOCALAPPDATA\\Programs\\node",
        "$env:ProgramFiles\\nodejs",
        "$env:USERPROFILE\\AppData\\Local\\Microsoft\\WindowsApps"
    )
    foreach ($d in $nodeDirs) { if (Test-Path $d) { $env:Path = $d + ';' + $env:Path } }
    if (Test-Command node) {
        $nodeVersion = node --version
        Write-Host "[OK] Node.js $nodeVersion detecte apres installation" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Node.js non detecte. Ouvrez un nouveau terminal PowerShell et relancez le script." -ForegroundColor Yellow
        exit
    }
}

# 2b. Installer Tesseract OCR (requis pour OCR)
Write-Host "`n[2b/8] Verification de Tesseract OCR..." -ForegroundColor Yellow
if (Test-Command tesseract) {
    $tessVersion = tesseract --version | Select-Object -First 1
    Write-Host "[OK] $tessVersion" -ForegroundColor Green
} else {
    Write-Host "[ERREUR] Tesseract non trouve. Installation..." -ForegroundColor Red
    winget install -e --id Tesseract.TesseractOCR
    Write-Host "[WARN] Si 'tesseract' n'est pas reconnu, redemarrez PowerShell." -ForegroundColor Yellow
}

# 3. Créer l'environnement virtuel Python (prefere Python 3.11)
Write-Host "`n[3/8] Configuration de l'environnement Python..." -ForegroundColor Yellow
Push-Location backend

if (Test-Path "venv") {
    Write-Host "[OK] Environnement virtuel deja existant" -ForegroundColor Green
} else {
    Write-Host "Creation de l'environnement virtuel (Python 3.11 si disponible)..." -ForegroundColor Cyan
    $venvCreated = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            py -3.11 --version | Out-Null
            if ($LASTEXITCODE -eq 0) {
                py -3.11 -m venv venv
                if ($LASTEXITCODE -eq 0) { $venvCreated = $true }
            }
        } catch { }
    }
    if (-not $venvCreated) {
        python -m venv venv
    }
    Write-Host "[OK] Environnement virtuel cree" -ForegroundColor Green
}

# 4. Installer les dépendances Python
Write-Host "`n[4/8] Installation des dependances Python..." -ForegroundColor Cyan
.\venv\Scripts\Activate.ps1
Write-Host ("Version Python active: " + (python --version)) -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Dependances Python installees" -ForegroundColor Green
} else {
    Write-Host "[WARN] Erreur lors de l'installation des dependances Python" -ForegroundColor Yellow
}

deactivate
Pop-Location

# 5. Installer les dépendances Node.js
Write-Host "`n[5/8] Installation des dependances Node.js..." -ForegroundColor Yellow
Push-Location frontend

if (Test-Path "node_modules") {
    Write-Host "node_modules existe deja, mise a jour..." -ForegroundColor Cyan
}

npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Dependances Node.js installees" -ForegroundColor Green
} else {
    Write-Host "[WARN] Erreur lors de l'installation des dependances Node.js" -ForegroundColor Yellow
}

Pop-Location

# 6. Créer les dossiers nécessaires
Write-Host "`n[6/8] Creation des dossiers..." -ForegroundColor Yellow
$folders = @("data", "logs", "data/exports")
foreach ($folder in $folders) {
    if (!(Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
    Write-Host "[OK] Cree: $folder" -ForegroundColor Green
    }
}

# 7. Initialiser la base de données
Write-Host "`n[7/8] Initialisation de la base de donnees..." -ForegroundColor Yellow
Push-Location backend
.\venv\Scripts\Activate.ps1

Write-Host "Test de la base de donnees..." -ForegroundColor Cyan
$dbTestScript = @"
import sys
import os
os.chdir('..')
sys.path.insert(0, os.getcwd() + '/backend')
from app.db import init_db, test_db_connection
init_db()
result = test_db_connection()
print('DB OK' if result else 'DB Error')
"@

python -c $dbTestScript

deactivate
Pop-Location

# 8. Résumé
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "[SUCCES] INSTALLATION TERMINEE !" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Prochaines etapes:`n" -ForegroundColor Yellow
Write-Host "1. Lancer le backend:" -ForegroundColor Cyan
Write-Host "   cd backend" -ForegroundColor White
Write-Host "   .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "   uvicorn app.main:app --reload`n" -ForegroundColor White

Write-Host "2. Dans un autre terminal, lancer le frontend:" -ForegroundColor Cyan
Write-Host "   cd frontend" -ForegroundColor White
Write-Host "   npm run electron:dev`n" -ForegroundColor White

Write-Host "3. Ou utilisez le script de lancement rapide:" -ForegroundColor Cyan
Write-Host "   .\scripts\start-dev.ps1`n" -ForegroundColor White

Write-Host "Documentation: README.md et NEXT_STEPS.md" -ForegroundColor Magenta
