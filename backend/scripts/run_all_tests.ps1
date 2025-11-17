# Test Runner Script - Execute all test suites (PowerShell)
# Phase 10: Tests, QA et Performance

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "DECLADO-IA - Test Suite Runner" -ForegroundColor Cyan
Write-Host "Phase 10: Tests, QA et Performance" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Change to backend directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath ".."
Set-Location $backendPath

# Run all tests with coverage
Write-Host ""
Write-Host "Running all tests with coverage..." -ForegroundColor Yellow
Write-Host ""

python -m pytest `
    --cov=app `
    --cov-report=html:htmlcov `
    --cov-report=term-missing `
    --cov-report=xml:coverage.xml `
    --cov-fail-under=80 `
    -v

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Tests failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Generate test report
Write-Host ""
Write-Host "Generating test report..." -ForegroundColor Yellow
python scripts/generate_test_report.py

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "✅ Test suite complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Reports generated:" -ForegroundColor Cyan
Write-Host "  - Coverage HTML: htmlcov/index.html"
Write-Host "  - Coverage XML:  coverage.xml"
Write-Host "  - Test Report:   TEST_REPORT.md"
Write-Host ""

