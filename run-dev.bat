@echo off
setlocal
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.12+ is required. Install Python and add it to PATH.
  exit /b 1
)
python scripts\start.py --dev %*
exit /b %errorlevel%
