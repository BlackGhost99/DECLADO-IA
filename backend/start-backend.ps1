# Script de démarrage du backend DECLADO-IA
# - Ajoute automatiquement Poppler (pdfinfo/pdftoppm) au PATH si trouvé
# - Respecte la variable d'environnement POPPLER_PATH si définie

Set-Location $PSScriptRoot

# ---------- Poppler detection (Windows) ----------
$popplerCandidates = @()
if ($env:POPPLER_PATH) { $popplerCandidates += $env:POPPLER_PATH }
$popplerCandidates += @(
	'C:\Program Files\poppler\Library\bin',
	'C:\Program Files\poppler\bin',
	'C:\Program Files (x86)\poppler\Library\bin',
	'C:\ProgramData\chocolatey\lib\poppler\tools',
	'C:\DECLADO-IA\Release-25.11.0-0\poppler-25.11.0\Library\bin',
	'C:\Release-25.11.0-0\poppler-25.11.0\Library\bin'
)

foreach ($p in $popplerCandidates) {
	if (-not [string]::IsNullOrEmpty($p) -and (Test-Path (Join-Path $p 'pdfinfo.exe'))) {
		$env:POPPLER_PATH = $p
		if (-not $env:PATH.Split(';') -contains $p) {
			$env:PATH = "$p;" + $env:PATH
		}
		Write-Host "✅ Poppler détecté: $p" -ForegroundColor Green
		break
	}
}

# Optional: display versions for debug (avoid non-ascii to prevent parsing issues)
try {
	$pdfinfo = (Get-Command 'pdfinfo.exe' -ErrorAction Stop).Source
	Write-Host ("INFO pdfinfo: " + $pdfinfo) -ForegroundColor DarkCyan
} catch {
	# ignore if not found in PATH
}

# ---------- Start backend ----------
& .\venv\Scripts\python.exe start.py
