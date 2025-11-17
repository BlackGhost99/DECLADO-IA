# Script to exclude test files from Windows Defender
# Run as Administrator

# Add exclusion for test files directory
$testDir = "C:\Users\BlackGhost\Desktop\DECLADO-IA\test_files"

# Create the directory if it doesn't exist
if (-not (Test-Path $testDir)) {
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
    Write-Host "✅ Created test directory: $testDir"
}

# Add exclusion to Windows Defender
try {
    Add-MpPreference -ExclusionPath $testDir
    Write-Host "✅ Added Defender exclusion: $testDir"
}
catch {
    Write-Host "⚠️  Could not add exclusion (requires Admin): $_"
    Write-Host "   Please run this script as Administrator"
}

# List current exclusions
Write-Host "`n📋 Current Defender exclusions:"
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
