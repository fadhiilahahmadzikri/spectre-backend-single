#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Spectre API Test Pipeline — Master Runner
.DESCRIPTION
    Executes the full test pipeline in order:
    1. Unit tests (pytest, mocked deps)
    2. Integration tests (pytest, real test DB)
    3. External validation (Newman, requires running server)
.PARAMETER Layer
    Which layer to run: "unit", "integration", "newman", or "all" (default)
.PARAMETER Coverage
    Generate HTML coverage report (default: $true)
.EXAMPLE
    .\scripts\run-tests.ps1 -Layer unit
    .\scripts\run-tests.ps1 -Layer all -Coverage $true
#>

param(
    [ValidateSet("unit", "integration", "newman", "all")]
    [string]$Layer = "all",
    [bool]$Coverage = $true
)

$ErrorActionPreference = "Stop"
# Set root to the directory containing the script
$root = Resolve-Path "$PSScriptRoot\.."
Set-Location $root

Write-Host "`n=== SPECTRE TEST PIPELINE ===" -ForegroundColor Cyan

# --- UNIT TESTS ---
if ($Layer -eq "unit" -or $Layer -eq "all") {
    Write-Host "`n[1/3] UNIT TESTS (mocked infrastructure)" -ForegroundColor White
    $covArgs = if ($Coverage) { @("--cov=src/spectre", "--cov-report=term-missing", "--cov-report=html:reports/coverage") } else { @() }
    python -m pytest tests/unit/ -v --tb=short @covArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "UNIT TESTS FAILED" -ForegroundColor Red
        exit 1
    }
    Write-Host "Unit tests passed." -ForegroundColor Green
}

# --- INTEGRATION TESTS ---
if ($Layer -eq "integration" -or $Layer -eq "all") {
    Write-Host "`n[2/3] INTEGRATION TESTS (test database)" -ForegroundColor White
    python -m pytest tests/integration/ -v --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "INTEGRATION TESTS FAILED" -ForegroundColor Red
        exit 1
    }
    Write-Host "Integration tests passed." -ForegroundColor Green
}

# --- NEWMAN (EXTERNAL VALIDATION) ---
if ($Layer -eq "newman" -or $Layer -eq "all") {
    Write-Host "`n[3/3] NEWMAN — External API Validation" -ForegroundColor White

    $newman = Get-Command newman -ErrorAction SilentlyContinue
    if (-not $newman) {
        Write-Host "  [SKIP] Newman not installed. Run: npm install -g newman" -ForegroundColor Yellow
    } else {
        if (-not (Test-Path reports)) { New-Item -ItemType Directory -Path reports | Out-Null }
        newman run tests/postman/spectre-api-v1.postman_collection.json `
            -e tests/postman/env-local.json `
            --reporters cli `
            --timeout-request 10000 `
            --delay-request 100
        if ($LASTEXITCODE -ne 0) {
            Write-Host "NEWMAN TESTS FAILED" -ForegroundColor Red
            exit 1
        }
        Write-Host "Newman tests passed." -ForegroundColor Green
    }
}

Write-Host "`n=== ALL TESTS PASSED ===" -ForegroundColor Green
exit 0
