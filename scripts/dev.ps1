# Start the MIAP backend and frontend together for local development.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -ModelBackend stub -BackendPort 8010 -FrontendPort 5174
# Ctrl+C stops both servers.

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [ValidateSet("torch", "stub")]
    [string]$ModelBackend = "torch"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

if (-not (Test-Path $python)) {
    throw "Python environment not found at $python. Create it with: python -m venv .venv; .venv\Scripts\pip install -r backend\requirements.txt"
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    throw "Frontend dependencies are missing. Run: cd frontend; npm install"
}

$env:MIAP_MODEL_BACKEND = $ModelBackend

Write-Host "Starting backend  http://127.0.0.1:$BackendPort  (model backend: $ModelBackend)"
$backend = Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload" `
    -WorkingDirectory $backendDir -PassThru

Write-Host "Starting frontend http://localhost:$FrontendPort"
$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev", "--", "--port", "$FrontendPort" `
    -WorkingDirectory $frontendDir -PassThru

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($backend.HasExited) { throw "Backend exited during startup. Check the backend window for the error." }
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/healthz" -TimeoutSec 2
        if ($response.status -eq "ok") { $ready = $true; break }
    } catch {
        # not listening yet
    }
}
if (-not $ready) {
    throw "Backend did not become healthy on port $BackendPort within 30 seconds."
}

Write-Host ""
Write-Host "MIAP is running. Open http://localhost:$FrontendPort"
Write-Host "Demo accounts (development only): clinician@miap.local, researcher@miap.local, admin@miap.local"
Write-Host "Press Ctrl+C to stop both servers."
Write-Host ""

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($backend.HasExited) { throw "Backend stopped (exit code $($backend.ExitCode))." }
        if ($frontend.HasExited) { throw "Frontend stopped (exit code $($frontend.ExitCode))." }
    }
} finally {
    foreach ($process in @($frontend, $backend)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Stopped MIAP."
}
