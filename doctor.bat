@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not defined PIXFABRICA_WEB_PORT set PIXFABRICA_WEB_PORT=5173
if not defined PIXFABRICA_API_PORT set PIXFABRICA_API_PORT=8000

set FAIL=0
set PORTS_IN_USE=0

echo Pixfabrica doctor
echo =================
echo.

where uv >nul 2>&1
if errorlevel 1 (
  echo X uv              not found - https://docs.astral.sh/uv/getting-started/installation/
  set FAIL=1
) else (
  for /f "delims=" %%v in ('uv --version 2^>nul') do echo OK uv              %%v
)

uv python find 3.12 >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo X Python 3.12     not found - run: uv python install 3.12
    set FAIL=1
  ) else (
    for /f "delims=" %%p in ('python --version 2^>^&1') do echo OK Python 3.12     %%p
  )
) else (
  echo OK Python 3.12     available via uv
)

where pnpm >nul 2>&1
if errorlevel 1 (
  echo X pnpm            not found - https://pnpm.io/installation
  set FAIL=1
) else (
  for /f "delims=" %%p in ('pnpm --version 2^>nul') do echo OK pnpm            %%p
)

echo.

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo WARN ffmpeg          not on PATH - editor works; renders will fail
) else (
  echo OK ffmpeg          on PATH
)

uv run python -c "from pixfabrica_renderer.gl_probe import gl_available; raise SystemExit(0 if gl_available() else 1)" >nul 2>&1
if errorlevel 1 (
  echo WARN opengl          not available - GL tracks and GPU effects disabled
) else (
  echo OK opengl          context available
)

curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo WARN ollama          not reachable - compose agent disabled
) else (
  echo OK ollama          reachable at http://127.0.0.1:11434
)

echo.

netstat -an | findstr /R /C:":%PIXFABRICA_WEB_PORT% .*LISTENING" >nul 2>&1
if errorlevel 1 (
  echo OK port %PIXFABRICA_WEB_PORT% web   available
) else (
  echo WARN port %PIXFABRICA_WEB_PORT% web   in use - close the other dev server
  set PORTS_IN_USE=1
)

netstat -an | findstr /R /C:":%PIXFABRICA_API_PORT% .*LISTENING" >nul 2>&1
if errorlevel 1 (
  echo OK port %PIXFABRICA_API_PORT% api   available
) else (
  echo WARN port %PIXFABRICA_API_PORT% api   in use - close the other dev server
  set PORTS_IN_USE=1
)

if "%PORTS_IN_USE%"=="1" (
  echo.
  echo Ports busy? Usually a previous run-all / pnpm dev:all is still running.
  echo Windows: run stop-all.bat from the repo root, or: cd web ^&^& pnpm kill-dev
  echo Or pick different ports before run-all.bat:
  echo   set PIXFABRICA_WEB_PORT=5174
  echo   set PIXFABRICA_API_PORT=8001
  echo   run-all.bat
  echo Or copy web\.env.example to web\.env and edit the port numbers there.
)

echo.

if "%FAIL%"=="1" (
  echo Doctor failed - fix the items marked X above.
  exit /b 1
)

echo Doctor passed - run setup.bat next (or run-all.bat if already set up).
exit /b 0
