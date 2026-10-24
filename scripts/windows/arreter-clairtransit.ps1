# ClairTransit : arrêt de ce que demarrer-clairtransit.ps1 a lancé (API, interface, base).
#   powershell -ExecutionPolicy Bypass -File .\arreter-clairtransit.ps1
# Ne touche à aucun autre programme : chaque PID est vérifié avec son heure de démarrage.

param([string]$Dossier = (Join-Path $env:LOCALAPPDATA "ClairTransit"))

$FichierEtat = Join-Path $Dossier "etat.json"
if (Test-Path $FichierEtat) {
    $etat = Get-Content $FichierEtat -Raw | ConvertFrom-Json
    foreach ($p in @($etat.processus)) {
        $proc = Get-Process -Id $p.pid -ErrorAction SilentlyContinue
        if ($proc -and $proc.StartTime.ToString("o") -eq $p.debut) {
            Write-Host "Arrêt : $($p.nom) (PID $($p.pid))"
            & taskkill.exe /PID $p.pid /T /F | Out-Null
        }
    }
    Remove-Item $FichierEtat -Force
}
$pgCtl = Join-Path $Dossier "outils\pgsql\bin\pg_ctl.exe"
$pgDonnees = Join-Path $Dossier "donnees\postgres"
if ((Test-Path $pgCtl) -and (Test-Path (Join-Path $pgDonnees "postmaster.pid"))) {
    & $pgCtl -D $pgDonnees status | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Arrêt : base PostgreSQL"
        & $pgCtl -D $pgDonnees -m fast -w stop | Out-Null
    }
}
Write-Host "ClairTransit est arrêté. Les données restent dans $Dossier."
Read-Host "Appuie sur Entrée pour fermer cette fenêtre"
