@echo off
cd /d "%~dp0"

if not defined PIXFABRICA_WEB_PORT set PIXFABRICA_WEB_PORT=5173
if not defined PIXFABRICA_API_PORT set PIXFABRICA_API_PORT=8000

netstat -an | findstr /R /C:":%PIXFABRICA_WEB_PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo WARN: port %PIXFABRICA_WEB_PORT% already in use - run stop-all.bat first if a previous session is stuck.
)
netstat -an | findstr /R /C:":%PIXFABRICA_API_PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo WARN: port %PIXFABRICA_API_PORT% already in use - run stop-all.bat first if a previous session is stuck.
)

echo Starting Pixfabrica (Vite + API)...
echo Editor:   http://localhost:%PIXFABRICA_WEB_PORT%
echo API docs: http://localhost:%PIXFABRICA_API_PORT%/docs
echo.
echo Stop with Ctrl+C in this window. If you close the window instead, run stop-all.bat.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:%PIXFABRICA_WEB_PORT%"

cd /d "%~dp0web"
pnpm dev:all
