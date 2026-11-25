# Start the whole app: backend (FastAPI, :8000) and frontend (Vite, :5173) in one console.
# Usage from the repo root:  .\dev            (or: .\dev -NoBrowser, .\dev -Install)
# Ctrl+C stops both.
param(
    [switch]$NoBrowser,  # do not open the browser
    [switch]$Install     # force `npm install` even if node_modules exists
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# --- Checks and one-time setup -------------------------------------------------------
if (-not (Test-Command python)) { throw 'Python not found. Install Python, then: python -m pip install --user uv' }
if (-not (Test-Command node)) { throw 'Node.js not found. Install Node.js 22 or 24 LTS.' }
python -m uv --version *> $null
if ($LASTEXITCODE -ne 0) { throw 'uv not found. Run: python -m pip install --user uv' }

if (-not (Test-Path (Join-Path $backend '.env'))) {
    Copy-Item (Join-Path $backend '.env.example') (Join-Path $backend '.env')
    Write-Host 'Created backend\.env from .env.example' -ForegroundColor Yellow
}
if ($Install -or -not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host 'Installing frontend dependencies ...' -ForegroundColor Cyan
    npm install --prefix $frontend --no-package-lock
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
}

foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the other backend/frontend first."
    }
}

# --- Start both ----------------------------------------------------------------------
# `uv run` syncs the backend environment by itself; the backend checks/extracts the log
# package on start (first time ~1 min).
# No auto-reload here: on Windows uvicorn restarts its worker with Ctrl+C, which reaches every
# process in this console and would stop the whole app on each backend change or git pull.
$env:API_RELOAD = 'false'
Write-Host 'Starting backend on http://localhost:8000 ...' -ForegroundColor Cyan
$be = Start-Process python -ArgumentList '-m', 'uv', 'run', 'logtracer' `
    -WorkingDirectory $backend -NoNewWindow -PassThru
$fe = $null

try {
    $deadline = (Get-Date).AddMinutes(5)
    $ready = $false
    while (-not $ready -and (Get-Date) -lt $deadline -and -not $be.HasExited) {
        try {
            $null = Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2
            $ready = $true
        } catch { Start-Sleep -Seconds 1 }
    }
    if ($ready) {
        # Start the frontend only now, so its /api proxy never hits a backend that is not up yet.
        Write-Host 'Starting frontend on http://localhost:5173 ...' -ForegroundColor Cyan
        $fe = Start-Process npm.cmd -ArgumentList 'run', 'dev' `
            -WorkingDirectory $frontend -NoNewWindow -PassThru
        Write-Host ''
        Write-Host 'Log Tracer is running:' -ForegroundColor Green
        Write-Host '  App       http://localhost:5173' -ForegroundColor Green
        Write-Host '  API docs  http://localhost:8000/docs' -ForegroundColor Green
        Write-Host '  Ctrl+C stops both.' -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process 'http://localhost:5173' }
        while (-not $be.HasExited -and -not $fe.HasExited) { Start-Sleep -Seconds 1 }
    } else {
        Write-Host 'Backend did not become ready, see the output above.' -ForegroundColor Red
    }
} finally {
    # Stop both process trees (uvicorn reloader and Vite start child processes).
    foreach ($p in $be, $fe) {
        if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F *> $null }
    }
    Write-Host 'Stopped backend and frontend.' -ForegroundColor Yellow
}
