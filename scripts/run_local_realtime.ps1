# Demarre Redis, Celery et Daphne pour le temps reel en local (Windows)
# Usage :
#   .\scripts\run_local_realtime.bat
#   ou : powershell -ExecutionPolicy Bypass -File scripts\run_local_realtime.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\redis_windows.ps1"

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

if (-not (Test-RedisConnection)) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        Write-Host "Demarrage Redis via Docker..." -ForegroundColor Cyan
        docker compose -f docker-compose.redis.yml up -d
        Start-Sleep -Seconds 3
    }
}

if (-not (Test-RedisConnection)) {
    Write-Host ""
    Write-Host "Redis/Memurai indisponible sur le port 6379." -ForegroundColor Red
    Write-Host "Verifiez le service Memurai dans services.msc ou installez-le :"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\install_redis_windows.ps1"
    Write-Host ""
    Write-Host "Test manuel (CMD) :"
    Write-Host '  "C:\Program Files\Memurai\memurai-cli.exe" ping'
    Write-Host ""
    exit 1
}

Write-Host "Redis/Memurai OK (PONG)" -ForegroundColor Green

Write-Host "Installation des dependances Python..." -ForegroundColor Cyan
& (Join-Path (Split-Path $venvActivate) "python.exe") -m pip install -r requirements.txt -q

Write-Host "Demarrage du worker Celery (nouvelle fenetre)..." -ForegroundColor Cyan
$celeryCmd = "Set-Location '$ProjectRoot'; & '$venvActivate'; celery -A school worker -l info --pool=solo"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $celeryCmd)

Write-Host ""
Write-Host "Demarrage de Daphne sur http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "WebSocket : ws://127.0.0.1:8000/ws/realtime/" -ForegroundColor Yellow
Write-Host "Arret : Ctrl+C dans cette fenetre + fermer la fenetre Celery" -ForegroundColor Gray
Write-Host ""

& $venvActivate
daphne -b 127.0.0.1 -p 8000 school.asgi:application
