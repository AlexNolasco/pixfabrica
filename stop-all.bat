@echo off
cd /d "%~dp0"

if not defined PIXFABRICA_WEB_PORT set PIXFABRICA_WEB_PORT=5173
if not defined PIXFABRICA_API_PORT set PIXFABRICA_API_PORT=8000

echo Stopping Pixfabrica dev servers (ports %PIXFABRICA_WEB_PORT%, %PIXFABRICA_API_PORT%)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web\scripts\kill-dev-ports.ps1"
