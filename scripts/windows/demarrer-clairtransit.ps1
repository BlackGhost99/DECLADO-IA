# ClairTransit : installation et lancement de la nouvelle interface sur un PC Windows.
#
# Lancement (dans le dossier où se trouve ce fichier) :
#   powershell -ExecutionPolicy Bypass -File .\demarrer-clairtransit.ps1
#
# Ce que fait le script :
#   - tout est installé dans un seul dossier, par défaut %LOCALAPPDATA%\ClairTransit
#     (hors OneDrive, pour ne pas synchroniser des milliers de fichiers) ;
#   - rien n'est installé dans Windows : ni service, ni variable système, ni programme ;
#   - base PostgreSQL portable sur un port libre (55432 ou suivant), Python et Node portables ;
#   - antivirus ClamAV portable (signature Talos vérifiée par empreinte), écoute locale seulement :
#     sans lui, l'application refuse tout dépôt de fichier ;
#   - installation neuve : aucune société ni aucun compte. Au premier lancement, l'écran
#     « Mise en service » crée le compte de l'exploitant ClairTransit (double authentification) ;
#     les sociétés sont ensuite créées depuis sa console, ou après sa validation d'une demande ;
#   - clés secrètes générées sur ce PC, gardées dans donnees\cles.json (jamais dans le code).
# Pour tout supprimer : arreter-clairtransit.ps1, puis effacer le dossier d'installation.
#
# Options :
#   -Dossier <chemin>   autre dossier d'installation
#   -MettreAJour        retélécharge le code de la branche (les données sont conservées)
#   -Branche <nom>      branche du dépôt (défaut : mise-en-route)
#   -Demo               ajoute les comptes et le référentiel de démonstration (fictifs, marqués comme tels)

param(
    [string]$Dossier = (Join-Path $env:LOCALAPPDATA "ClairTransit"),
    [string]$Branche = "mise-en-route",
    [switch]$MettreAJour,
    [switch]$Demo
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Depot = "https://github.com/BlackGhost99/DECLADO-IA"
$UrlUv = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
$VersionNode = "v22.23.4"
$UrlNode = "https://nodejs.org/dist/$VersionNode/node-$VersionNode-win-x64.zip"
$VersionClamav = "1.5.4"
$UrlClamav = "https://github.com/Cisco-Talos/clamav/releases/download/clamav-$VersionClamav/clamav-$VersionClamav.win.x64.zip"
# Empreinte de l'archive officielle, contrôlée avec la signature GPG Talos (clé 707F0DB480836771).
$Sha256Clamav = "0d9e0228b2674137ea1a2853566c98a0278ad52ab2582c3d6dbd75373848c395"
$UrlPostgres = "https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-windows-amd64/16.9.0/embedded-postgres-binaries-windows-amd64-16.9.0.jar"
$MotDePasseDemo = "demo-ClairTransit-2026"

$Outils = Join-Path $Dossier "outils"
$Telechargements = Join-Path $Dossier "telechargements"
$Code = Join-Path $Dossier "code"
$Donnees = Join-Path $Dossier "donnees"
$Etapes = Join-Path $Dossier "etapes"
$Journaux = Join-Path $Dossier "journaux"
$FichierEtat = Join-Path $Dossier "etat.json"

function Titre([string]$texte) { Write-Host ""; Write-Host "== $texte" -ForegroundColor Cyan }
function Info([string]$texte) { Write-Host "   $texte" }

function Executer([string]$exe, [string[]]$arguments, [string]$message) {
    $ErrorActionPreference = "Continue"
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$message (code de sortie $LASTEXITCODE)" }
}

function Telecharger([string]$url, [string]$destination) {
    if (Test-Path $destination) { return }
    Info "Téléchargement : $url"
    $partiel = "$destination.partiel"
    for ($essai = 1; $essai -le 3; $essai++) {
        try {
            Invoke-WebRequest -Uri $url -OutFile $partiel -UseBasicParsing
            Move-Item -Force $partiel $destination
            return
        } catch {
            if ($essai -eq 3) { throw "Téléchargement impossible : $url ($($_.Exception.Message))" }
            Start-Sleep -Seconds (2 * $essai)
        }
    }
}

function Extraire-Zip([string]$zip, [string]$cible) {
    New-Item -ItemType Directory -Force $cible | Out-Null
    $tar = Join-Path $env:SystemRoot "System32\tar.exe"
    if (Test-Path $tar) {
        $ErrorActionPreference = "Continue"
        & $tar -xf $zip -C $cible
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -eq 0) { return }
    }
    Expand-Archive -Path $zip -DestinationPath $cible -Force
}

function Port-Libre([int]$depart) {
    for ($p = $depart; $p -lt $depart + 50; $p++) {
        $occupe = $false
        try { if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { $occupe = $true } } catch { }
        if ($occupe) { continue }
        try {
            # Écoute locale uniquement : pas d'alerte du pare-feu.
            $ecoute = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
            $ecoute.Start(); $ecoute.Stop()
            return $p
        } catch { }
    }
    throw "Aucun port libre trouvé à partir de $depart."
}

function Attendre-Port([int]$port, [int]$secondes, [string]$nom) {
    $limite = (Get-Date).AddSeconds($secondes)
    while ((Get-Date) -lt $limite) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect("127.0.0.1", $port); $client.Close()
            return
        } catch { Start-Sleep -Milliseconds 700 }
    }
    throw "$nom ne répond pas sur le port $port après $secondes secondes (voir sa fenêtre ou $Journaux)."
}

function Etape-Faite([string]$nom) { Test-Path (Join-Path $Etapes "$nom.ok") }
function Marquer-Etape([string]$nom) { Set-Content -Path (Join-Path $Etapes "$nom.ok") -Value (Get-Date -Format s) }

function Arreter-Precedent {
    # Arrête seulement ce que ce script a lui-même lancé (PID et heure de démarrage vérifiés).
    if (Test-Path $FichierEtat) {
        $etat = Get-Content $FichierEtat -Raw | ConvertFrom-Json
        foreach ($p in @($etat.processus)) {
            $proc = Get-Process -Id $p.pid -ErrorAction SilentlyContinue
            if ($proc -and $proc.StartTime.ToString("o") -eq $p.debut) {
                Info "Arrêt de l'instance précédente : $($p.nom) (PID $($p.pid))"
                & taskkill.exe /PID $p.pid /T /F | Out-Null
            }
        }
        Remove-Item $FichierEtat -Force
    }
    $pgCtl = Join-Path $Outils "pgsql\bin\pg_ctl.exe"
    $pgDonnees = Join-Path $Donnees "postgres"
    if ((Test-Path $pgCtl) -and (Test-Path (Join-Path $pgDonnees "postmaster.pid"))) {
        & $pgCtl -D $pgDonnees status | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Info "Arrêt de la base de l'instance précédente"
            & $pgCtl -D $pgDonnees -m fast -w stop | Out-Null
        }
    }
}

try {
    New-Item -ItemType Directory -Force $Dossier, $Outils, $Telechargements, $Donnees, $Etapes, $Journaux | Out-Null
    Start-Transcript -Path (Join-Path $Journaux "installation.txt") -Append | Out-Null

    Titre "ClairTransit, nouvelle interface (branche $Branche)"
    Info "Dossier d'installation : $Dossier"
    if (-not (Etape-Faite "accord")) {
        Info "Le premier lancement télécharge environ 120 Mo (Python, Node, PostgreSQL, code),"
        Info "environ 330 Mo pour l'antivirus ClamAV et ses signatures, puis environ 300 Mo de bibliothèques."
        Info "Il faut prévoir 2,5 Go d'espace disque."
        Info "Rien n'est installé dans Windows ; tout reste dans le dossier ci-dessus."
        $reponse = Read-Host "   Continuer ? (O/N)"
        if ($reponse -notmatch '^[oOyY]') { Info "Abandon, rien n'a été modifié."; return }
        Marquer-Etape "accord"
    }

    Titre "Arrêt d'une éventuelle instance précédente"
    Arreter-Precedent

    # Environnement limité à ce processus et aux fenêtres qu'il ouvre.
    $env:UV_CACHE_DIR = Join-Path $Dossier "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Outils "python"
    $env:UV_PYTHON_PREFERENCE = "only-managed"
    $env:npm_config_cache = Join-Path $Dossier "cache\npm"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Titre "Outils"
    $uv = Join-Path $Outils "uv\uv.exe"
    if (-not (Test-Path $uv)) {
        $zip = Join-Path $Telechargements "uv.zip"
        Telecharger $UrlUv $zip
        Extraire-Zip $zip (Join-Path $Outils "uv")
        if (-not (Test-Path $uv)) { $trouve = Get-ChildItem (Join-Path $Outils "uv") -Recurse -Filter uv.exe | Select-Object -First 1; Copy-Item $trouve.FullName $uv }
    }
    Info "uv : prêt"

    $venv = Join-Path $Outils "venv"
    $python = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Executer $uv @("python", "install", "3.13") "Installation de Python 3.13 impossible"
        Executer $uv @("venv", $venv, "--python", "3.13") "Création de l'environnement Python impossible"
    }
    Info "Python : $(& $python --version)"

    $node = $null
    $commandeNode = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($commandeNode) {
        $versionNode = (& $commandeNode.Source -v) -replace '^v', ''
        if ([int]($versionNode.Split('.')[0]) -ge 22) { $node = $commandeNode.Source; Info "Node déjà présent sur le PC : v$versionNode" }
    }
    if (-not $node) {
        $dossierNode = Join-Path $Outils "node-$VersionNode-win-x64"
        if (-not (Test-Path (Join-Path $dossierNode "node.exe"))) {
            $zip = Join-Path $Telechargements "node-$VersionNode.zip"
            Telecharger $UrlNode $zip
            Extraire-Zip $zip $Outils
        }
        $node = Join-Path $dossierNode "node.exe"
        Info "Node portable : $VersionNode"
    }
    $env:Path = (Split-Path $node) + ";" + $env:Path
    $npmCli = Join-Path (Split-Path $node) "node_modules\npm\bin\npm-cli.js"

    $pgBin = Join-Path $Outils "pgsql\bin"
    if (-not (Test-Path (Join-Path $pgBin "postgres.exe"))) {
        $jar = Join-Path $Telechargements "postgres-16.9.jar"
        Telecharger $UrlPostgres $jar
        $tmp = Join-Path $Telechargements "postgres-extrait"
        Copy-Item -Force $jar "$jar.zip"
        Expand-Archive -Path "$jar.zip" -DestinationPath $tmp -Force
        Remove-Item -Force "$jar.zip"
        $txz = Get-ChildItem $tmp -Filter *.txz | Select-Object -First 1
        $script = Join-Path $Outils "extraire_txz.py"
        Set-Content -Path $script -Encoding ASCII -Value @'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:xz") as archive:
    archive.extractall(sys.argv[2], filter="data")
'@
        Executer $python @("-I", $script, $txz.FullName, (Join-Path $Outils "pgsql")) "Extraction de PostgreSQL impossible"
        Remove-Item -Recurse -Force $tmp
    }
    # PostgreSQL a besoin du runtime Visual C++ ; s'il manque dans Windows, on prend celui fourni avec Python.
    if (-not (Test-Path (Join-Path $env:SystemRoot "System32\vcruntime140.dll"))) {
        Get-ChildItem $env:UV_PYTHON_INSTALL_DIR -Recurse -Filter "vcruntime140*.dll" -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item -Force $_.FullName $pgBin }
    }
    Info "PostgreSQL portable : prêt"

    $clamDossier = Join-Path $Outils "clamav"
    $clamd = Join-Path $clamDossier "clamd.exe"
    if (-not (Test-Path $clamd)) {
        $zip = Join-Path $Telechargements "clamav-$VersionClamav.zip"
        Telecharger $UrlClamav $zip
        $empreinte = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
        if ($empreinte -ne $Sha256Clamav) {
            Remove-Item -Force $zip
            throw "Archive ClamAV inattendue (empreinte $empreinte) : elle a été supprimée, rien n'est installé."
        }
        $tmp = Join-Path $Telechargements "clamav-extrait"
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Extraire-Zip $zip $tmp
        $racine = Get-ChildItem $tmp -Directory | Select-Object -First 1
        Move-Item $racine.FullName $clamDossier
        Remove-Item -Recurse -Force $tmp
        # Les fichiers de débogage (.pdb) et bibliothèques de compilation (.lib) ne servent pas à l'exécution.
        Get-ChildItem $clamDossier -Recurse -Include *.pdb, *.lib | Remove-Item -Force
    }
    $clamBase = Join-Path $Donnees "clamav"
    New-Item -ItemType Directory -Force $clamBase | Out-Null
    $freshclamConf = Join-Path $clamDossier "freshclam.conf"
    Set-Content -Path $freshclamConf -Encoding ASCII -Value @"
DatabaseDirectory $clamBase
UpdateLogFile $(Join-Path $Journaux "freshclam.txt")
DatabaseMirror database.clamav.net
"@
    Titre "Signatures antivirus"
    $ErrorActionPreference = "Continue"
    & (Join-Path $clamDossier "freshclam.exe") "--config-file=$freshclamConf" "--stdout" | Out-Host
    $miseAJour = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $signatures = @(Get-ChildItem $clamBase -Include *.cvd, *.cld -Recurse -ErrorAction SilentlyContinue)
    if ($signatures.Count -eq 0) {
        throw "Aucune signature antivirus : la première installation a besoin d'Internet pour les télécharger (database.clamav.net)."
    }
    if ($miseAJour -ne 0) { Info "Mise à jour des signatures impossible (hors ligne ?) : les signatures déjà présentes sont utilisées." }
    Info "ClamAV $VersionClamav : prêt"

    Titre "Code de l'application"
    $marqueCode = Join-Path $Code "backend\manage.py"
    if ($MettreAJour -or -not (Test-Path $marqueCode)) {
        $zip = Join-Path $Telechargements "code-$Branche.zip"
        if (Test-Path $zip) { Remove-Item -Force $zip }
        Telecharger "$Depot/archive/refs/heads/$Branche.zip" $zip
        $tmp = Join-Path $Telechargements "code-extrait"
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Extraire-Zip $zip $tmp
        $racine = Get-ChildItem $tmp -Directory | Select-Object -First 1
        if (Test-Path $Code) { Remove-Item -Recurse -Force $Code }
        Move-Item $racine.FullName $Code
        Remove-Item -Recurse -Force $tmp
        if (Test-Path (Join-Path $Etapes "dependances.ok")) { Remove-Item (Join-Path $Etapes "dependances.ok") }
        Info "Code téléchargé (branche $Branche)"
    } else {
        Info "Code déjà présent (relancer avec -MettreAJour pour le rafraîchir)"
    }
    $backend = Join-Path $Code "backend"
    $frontend = Join-Path $Code "frontend"

    if (-not (Etape-Faite "dependances")) {
        Titre "Bibliothèques (premier lancement ou mise à jour, quelques minutes)"
        Executer $uv @("pip", "install", "--python", $python, "-r", (Join-Path $backend "requirements.txt")) "Installation des bibliothèques Python impossible"
        Push-Location $frontend
        try { Executer $node @($npmCli, "ci", "--no-audit", "--no-fund") "Installation des bibliothèques de l'interface impossible" }
        finally { Pop-Location }
        Marquer-Etape "dependances"
    }

    Titre "Base de données"
    $pgDonnees = Join-Path $Donnees "postgres"
    if (-not (Test-Path (Join-Path $pgDonnees "PG_VERSION"))) {
        Executer (Join-Path $pgBin "initdb.exe") @("-D", $pgDonnees, "-U", "clairtransit", "--auth=trust", "-E", "UTF8", "--locale=C") "Initialisation de la base impossible"
    }
    $portBase = Port-Libre 55432
    $journalPg = Join-Path $Journaux "postgres.txt"
    # Fenêtre cachée : la base continue de tourner si cette fenêtre est fermée.
    $pg = Start-Process -FilePath (Join-Path $pgBin "pg_ctl.exe") -WindowStyle Hidden -PassThru `
        -ArgumentList "-D `"$pgDonnees`" -l `"$journalPg`" -w -o `"-p $portBase -h 127.0.0.1`" start"
    $null = $pg.Handle
    $pg.WaitForExit()
    if ($pg.ExitCode -ne 0) { throw "Démarrage de PostgreSQL impossible, voir $journalPg" }
    Attendre-Port $portBase 30 "PostgreSQL"
    Info "PostgreSQL démarré sur 127.0.0.1:$portBase"

    $script = Join-Path $Outils "creer_base.py"
    Set-Content -Path $script -Encoding ASCII -Value @'
import sys
import psycopg
with psycopg.connect(host="127.0.0.1", port=int(sys.argv[1]), user="clairtransit", dbname="postgres", autocommit=True) as conn:
    if not conn.execute("select 1 from pg_database where datname = 'clairtransit'").fetchone():
        conn.execute("create database clairtransit")
'@
    Executer $python @("-I", $script, "$portBase") "Création de la base clairtransit impossible"

    $portClamav = Port-Libre 3310
    $clamdConf = Join-Path $clamDossier "clamd.conf"
    Set-Content -Path $clamdConf -Encoding ASCII -Value @"
DatabaseDirectory $clamBase
LogFile $(Join-Path $Journaux "clamd.txt")
TCPSocket $portClamav
TCPAddr 127.0.0.1
Foreground yes
StreamMaxLength 60M
"@
    # Fenêtre cachée ; l'arrêt passe par etat.json, comme l'API et l'interface.
    $antivirus = Start-Process -FilePath $clamd -WindowStyle Hidden -PassThru -ArgumentList "--config-file=`"$clamdConf`""
    Info "Chargement des signatures antivirus (jusqu'à deux minutes)…"

    $portApi = Port-Libre 8000
    $portInterface = Port-Libre 5173
    if ($portInterface -eq $portApi) { $portInterface = Port-Libre ($portApi + 1) }

    # Clés propres à cette installation, créées une seule fois. Les perdre rend illisibles
    # les secrets de double authentification : elles suivent les sauvegardes du dossier donnees.
    $fichierCles = Join-Path $Donnees "cles.json"
    if (-not (Test-Path $fichierCles)) {
        $script = Join-Path $Outils "generer_cles.py"
        Set-Content -Path $script -Encoding ASCII -Value @'
import json, secrets, sys
from cryptography.fernet import Fernet
with open(sys.argv[1], "x", encoding="ascii") as fichier:
    json.dump({"django": secrets.token_urlsafe(50), "mfa": Fernet.generate_key().decode("ascii")}, fichier)
'@
        Executer $python @("-I", $script, $fichierCles) "Création des clés de l'installation impossible"
        Info "Clés de l'installation créées : $fichierCles"
    }
    $cles = Get-Content $fichierCles -Raw | ConvertFrom-Json

    $env:DJANGO_DEBUG = "true"
    $env:DJANGO_SECRET_KEY = $cles.django
    $env:MFA_ENCRYPTION_KEY = $cles.mfa
    $env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
    $env:DATABASE_URL = "postgres://clairtransit@127.0.0.1:$portBase/clairtransit"
    $env:CELERY_TASK_ALWAYS_EAGER = "true"
    $env:CELERY_BROKER_URL = "memory://"
    $env:CSRF_TRUSTED_ORIGINS = "http://127.0.0.1:$portInterface,http://localhost:$portInterface"
    $env:PRIVATE_STORAGE_ROOT = Join-Path $Donnees "fichiers"
    $env:AI_PROVIDER = "disabled"
    $env:CLAMAV_HOST = "127.0.0.1"
    $env:CLAMAV_PORT = "$portClamav"
    $env:VITE_API_PROXY = "http://127.0.0.1:$portApi"

    Push-Location $backend
    try {
        Executer $python @("manage.py", "migrate", "--noinput") "Migration de la base impossible"
        if ($Demo -and -not (Etape-Faite "demo")) {
            Titre "Données de démonstration (fictives)"
            Executer $python @("manage.py", "import_tariff_csv", "..\fixtures\synthetic\referentiel-f.csv", "--label", "Jeu F (CSV fictif)") "Import du référentiel fictif impossible"
            $script = Join-Path $Outils "publier_demo.py"
            Set-Content -Path $script -Encoding UTF8 -Value @"
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from apps.tariffs.models import PublicationState, TariffEdition
from apps.tariffs.services import publish_edition

User = get_user_model()
email = "referentiel@demo.demo"
actor = User.objects.filter(email=email).first()
if actor is None:
    # Même compte que seed_demo, créé avant lui pour que le dossier fictif cible l'édition publiée.
    actor = User.objects.create_user(email=email, password="$MotDePasseDemo", full_name="Gestionnaire du référentiel", is_reference_manager=True)
for edition in TariffEdition.objects.filter(label="Jeu F (CSV fictif)", publication_state=PublicationState.DRAFT):
    publish_edition(edition=edition, actor=actor, mode=PublicationState.CONSULTATION)
    print("Édition publiée pour consultation :", edition.label)
"@
            Executer $python @($script) "Publication du référentiel fictif impossible"
            Executer $python @("manage.py", "seed_demo") "Création des comptes de démonstration impossible"
            Marquer-Etape "demo"
        }
    } finally { Pop-Location }

    Titre "Lancement"
    $api = Start-Process -FilePath $python -WorkingDirectory $backend -PassThru `
        -ArgumentList "manage.py runserver 127.0.0.1:$portApi"
    $interface = Start-Process -FilePath $node -WorkingDirectory $frontend -PassThru `
        -ArgumentList "node_modules\vite\bin\vite.js --port $portInterface --strictPort"
    $etat = @{
        dossier = $Dossier
        processus = @(
            @{ nom = "Antivirus"; pid = $antivirus.Id; debut = $antivirus.StartTime.ToString("o") },
            @{ nom = "API"; pid = $api.Id; debut = $api.StartTime.ToString("o") },
            @{ nom = "Interface"; pid = $interface.Id; debut = $interface.StartTime.ToString("o") }
        )
    }
    $etat | ConvertTo-Json -Depth 4 | Set-Content -Path $FichierEtat -Encoding UTF8
    Attendre-Port $portApi 60 "L'API"
    Attendre-Port $portInterface 60 "L'interface"
    Attendre-Port $portClamav 180 "L'antivirus ClamAV"

    $adresse = "http://127.0.0.1:$portInterface"
    Start-Process $adresse
    Titre "C'est prêt"
    Info "Adresse      : $adresse"
    if (Etape-Faite "demo") {
        Info "Cette installation contient les données de démonstration (fictives)."
        Info "Compte       : validateur@alpha.demo   (autres comptes : declarant@alpha.demo, admin@alpha.demo)"
        Info "Mot de passe : $MotDePasseDemo"
        if (-not $Demo) { Info "Pour une installation neuve, sans démonstration : relancer avec -Dossier <un nouveau dossier>." }
    } else {
        Info "Installation neuve : au premier lancement, l'écran « Mise en service » crée le compte exploitant."
        Info "Il faut une application d'authentification (téléphone) pour la double authentification."
        Info "Le référentiel tarifaire est vide : la recherche tarifaire attend l'import de la source officielle."
    }
    Info "Deux fenêtres restent ouvertes (API et interface) : ne pas les fermer pendant l'utilisation."
    Info "L'antivirus ClamAV tourne sans fenêtre, sur 127.0.0.1:$portClamav ; tout fichier déposé passe par lui."
    Info "Pour tout arrêter : powershell -ExecutionPolicy Bypass -File .\arreter-clairtransit.ps1"
    Info "La lecture des scans (OCR) n'est pas installée ici : les PDF à texte fonctionnent, les scans seront signalés."
} catch {
    Write-Host ""
    Write-Host "ERREUR : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Copie ce message (ou le fichier $Journaux\installation.txt) et envoie-le dans la conversation." -ForegroundColor Yellow
} finally {
    try { Stop-Transcript | Out-Null } catch { }
    Read-Host "Appuie sur Entrée pour fermer cette fenêtre"
}
