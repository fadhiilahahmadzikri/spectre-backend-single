#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Spectre API Test Pipeline — Dependency Audit
.DESCRIPTION
    Checks all runtimes, tools, and packages required to run the full
    pytest + Postman/Newman testing pipeline. Run once before any test execution.
#>

$ErrorActionPreference = "Continue"
$pass = 0
$fail = 0
$warn = 0

function CheckRuntime($name, $cmd, $required = $true) {
    try {
        $result = Invoke-Expression $cmd 2>&1
        if ($LASTEXITCODE -ne 0) {
            if ($required) {
                Write-Host "  [FAIL] $name" -ForegroundColor Red
                $script:fail++
            } else {
                Write-Host "  [WARN] $name - not found (optional)" -ForegroundColor Yellow
                $script:warn++
            }
        } else {
            $ver = ($result | Select-String -Pattern '\d+\.\d+' | Select-Object -First 1).Matches.Value
            Write-Host "  [PASS] $name ($ver)" -ForegroundColor Green
            $script:pass++
        }
    } catch {
        if ($required) {
            Write-Host "  [FAIL] $name - error" -ForegroundColor Red
            $script:fail++
        } else {
            Write-Host "  [WARN] $name - not found (optional)" -ForegroundColor Yellow
            $script:warn++
        }
    }
}

function CheckPythonPackage($pkg, $required = $true) {
    $pyCmd = "import $pkg; print(getattr($pkg, '__version__', 'installed'))"
    $out = python -c "$pyCmd" 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($required) {
            Write-Host "  [FAIL] python: $pkg" -ForegroundColor Red
            $script:fail++
        } else {
            Write-Host "  [WARN] python: $pkg - not installed (optional)" -ForegroundColor Yellow
            $script:warn++
        }
    } else {
        $ver = ($out | Select-String -Pattern '[\d\.]+' | Select-Object -First 1).Matches.Value
        if (-not $ver) { $ver = "ok" }
        Write-Host "  [PASS] python: $pkg ($ver)" -ForegroundColor Green
        $script:pass++
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " SPECTRE TEST PIPELINE - DEPENDENCY AUDIT" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# --- SECTION 1: RUNTIMES ---
Write-Host "[1/5] RUNTIMES" -ForegroundColor White
CheckRuntime "Python 3.11+" "python --version"
CheckRuntime "Node.js (for Newman)" "node --version" $false
CheckRuntime "npm" "npm --version" $false

# --- SECTION 2: PYTHON TEST PACKAGES ---
Write-Host "`n[2/5] PYTHON TEST PACKAGES (required)" -ForegroundColor White
CheckPythonPackage "pytest"
CheckPythonPackage "httpx"
CheckPythonPackage "pytest_asyncio"
CheckPythonPackage "pytest_cov"

Write-Host "`n[2b/5] PYTHON TEST PACKAGES (optional)" -ForegroundColor White
CheckPythonPackage "factory" $false
CheckPythonPackage "faker" $false
CheckPythonPackage "pytest_mock" $false
CheckPythonPackage "aiosqlite" $false
CheckPythonPackage "respx" $false

# --- SECTION 3: APPLICATION PACKAGES ---
Write-Host "`n[3/5] APPLICATION PACKAGES" -ForegroundColor White
CheckPythonPackage "fastapi"
CheckPythonPackage "pydantic"
CheckPythonPackage "sqlalchemy"
CheckPythonPackage "redis"
CheckPythonPackage "jose"
CheckPythonPackage "passlib"
CheckPythonPackage "pyotp"
CheckPythonPackage "cryptography"

# --- SECTION 4: NEWMAN / POSTMAN CLI ---
Write-Host "`n[4/5] NEWMAN (Postman CLI)" -ForegroundColor White
CheckRuntime "newman" "newman --version" $false
CheckRuntime "newman-reporter-htmlextra" "npm list -g newman-reporter-htmlextra --depth=0" $false

# --- SECTION 5: INFRASTRUCTURE ---
Write-Host "`n[5/5] INFRASTRUCTURE" -ForegroundColor White
CheckRuntime "Docker" "docker --version" $false
CheckRuntime "docker-compose" "docker compose version" $false

# Check if test Postgres is reachable
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("localhost", 5433)
    $tcp.Close()
    Write-Host "  [PASS] PostgreSQL test (port 5433)" -ForegroundColor Green
    $pass++
} catch {
    Write-Host "  [WARN] PostgreSQL test (port 5433) - not running" -ForegroundColor Yellow
    $warn++
}

# Check if test Redis is reachable
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("localhost", 6380)
    $tcp.Close()
    Write-Host "  [PASS] Redis test (port 6380)" -ForegroundColor Green
    $pass++
} catch {
    Write-Host "  [WARN] Redis test (port 6380) - not running" -ForegroundColor Yellow
    $warn++
}

# --- SUMMARY ---
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " RESULTS: $pass passed, $fail failed, $warn warnings" -ForegroundColor $(if ($fail -gt 0) { "Red" } else { "Green" })
Write-Host "========================================`n" -ForegroundColor Cyan

if ($fail -gt 0) {
    Write-Host "FIX REQUIRED - install missing dependencies before running tests." -ForegroundColor Red
    Write-Host "`nQuick fix commands:" -ForegroundColor Yellow
    Write-Host "  pip install -e '.[dev]'" -ForegroundColor Yellow
    Write-Host "  pip install aiosqlite respx faker" -ForegroundColor Yellow
    Write-Host "  npm install -g newman newman-reporter-htmlextra" -ForegroundColor Yellow
    Write-Host "  docker compose -f docker-compose.test.yml up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host "All required dependencies present. Ready to build test pipeline." -ForegroundColor Green
exit 0
