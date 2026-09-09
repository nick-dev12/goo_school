@echo off
REM Lance Daphne + Celery avec Redis pour le temps reel local (Windows)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_local_realtime.ps1"
pause
