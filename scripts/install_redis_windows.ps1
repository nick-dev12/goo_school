# Installe Redis pour Windows (Memurai Developer — compatible Redis)
# Usage : powershell -ExecutionPolicy Bypass -File scripts/install_redis_windows.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\redis_windows.ps1"

Write-Host "=== Installation Redis pour Aria (Windows) ===" -ForegroundColor Cyan

if (Test-RedisConnection) {
    try {
        $pong = Invoke-RedisPing
        Write-Host "Redis/Memurai deja actif ($pong)" -ForegroundColor Green
    } catch {
        Write-Host "Port 6379 ouvert — Memurai semble actif." -ForegroundColor Green
    }
    exit 0
}

Write-Host "Redis non detecte. Tentative via winget (Memurai Developer)..." -ForegroundColor Yellow

$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($winget) {
    winget install --id Memurai.MemuraiDeveloper -e --accept-source-agreements --accept-package-agreements
    Start-Sleep -Seconds 5
    if (Test-RedisConnection) {
        Write-Host "Memurai installe et actif." -ForegroundColor Green
        exit 0
    }
}

Write-Host ""
Write-Host "Options manuelles :" -ForegroundColor Yellow
Write-Host "  1. Memurai Developer : https://www.memurai.com/get-memurai"
Write-Host "  2. WSL : sudo apt install redis-server && sudo service redis-server start"
Write-Host "  3. Docker Desktop : docker compose -f docker-compose.redis.yml up -d"
Write-Host ""
Write-Host 'Test manuel (CMD) : "C:\Program Files\Memurai\memurai-cli.exe" ping' -ForegroundColor Cyan
