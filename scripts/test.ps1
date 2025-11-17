# ==========================================
# DECLADO-IA - Lanceur de Tests
# ==========================================

Write-Host "`n[DECLADO-IA] Lancement des tests`n" -ForegroundColor Cyan

$failed = 0

# Tests Backend
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[BACKEND] Tests Backend (Python/Pytest)" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

Push-Location backend
.\venv\Scripts\Activate.ps1
pytest -v --cov=app --cov-report=term-missing

if ($LASTEXITCODE -ne 0) {
    $failed++
    Write-Host "`n[FAIL] Tests backend echoues" -ForegroundColor Red
} else {
    Write-Host "`n[OK] Tests backend reussis" -ForegroundColor Green
}

deactivate
Pop-Location

# Tests Frontend
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "[FRONTEND] Tests Frontend (Vitest)" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

Push-Location frontend
npm test

if ($LASTEXITCODE -ne 0) {
    $failed++
    Write-Host "`n[FAIL] Tests frontend echoues" -ForegroundColor Red
} else {
    Write-Host "`n[OK] Tests frontend reussis" -ForegroundColor Green
}

Pop-Location

# Résumé
Write-Host "`n========================================" -ForegroundColor Cyan
if ($failed -eq 0) {
    Write-Host "[SUCCES] TOUS LES TESTS REUSSIS !" -ForegroundColor Green
} else {
    Write-Host "[FAIL] $failed suite(s) de tests echouee(s)" -ForegroundColor Red
}
Write-Host "========================================`n" -ForegroundColor Cyan

exit $failed
