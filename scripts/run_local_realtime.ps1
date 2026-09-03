# Démarre Redis (Docker), Celery et Daphne pour tester le temps réel en local.
# Usage : .\scripts\run_local_realtime.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Fichier .env cree depuis .env.example" -ForegroundColor Green
}

$venvActivate = Join-Path $ProjectRoot "env\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    $venvActivate = Join-Path $ProjectRoot "venv\Scripts\Activate.ps1"
}
if (-not (Test-Path $venvActivate)) {
    Write-Error "Environnement virtuel introuvable (env/ ou venv/)"
}

Write-Host "Demarrage de Redis via Docker..." -ForegroundColor Cyan
docker compose -f docker-compose.redis.yml up -d
Start-Sleep -Seconds 2

Write-Host "Verification Redis..." -ForegroundColor Cyan
docker exec goo_school_redis redis-cli ping

Write-Host "Demarrage du worker Celery (nouvelle fenetre)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectRoot'; & '$venvActivate'; celery -A school worker -l info --pool=solo"
)

Write-Host "Demarrage de Daphne sur http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Write-Host "WebSocket : ws://127.0.0.1:8000/ws/realtime/" -ForegroundColor Yellow
& $venvActivate
daphne -b 127.0.0.1 -p 8000 school.asgi:application
