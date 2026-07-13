@echo off
cd /d "%~dp0"

echo Running doctor...
call "%~dp0doctor.bat"
if errorlevel 1 exit /b 1

echo.
echo Installing Python packages...
uv sync --all-packages
if errorlevel 1 exit /b 1

echo.
echo Installing web packages...
cd /d "%~dp0web"
pnpm install
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Run run-all.bat to start the editor.
exit /b 0
