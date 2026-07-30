@echo off
title AFO Rig Console
cd /d %~dp0

rem If the console is already running, just open the browser to it.
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 8321 -State Listen -ErrorAction SilentlyContinue){exit 1}else{exit 0}" >nul 2>&1
if errorlevel 1 (
  echo The console is already running - opening http://localhost:8321
  start "" http://localhost:8321
  echo.
  pause
  exit /b 0
)

if not exist .venv\Scripts\python.exe (
  echo First run: creating the Python environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
  .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

echo.
echo   AFO Rig Console   -   http://localhost:8321
echo   Press Ctrl+C or close this window to stop the server.
echo.
start "" http://localhost:8321
.venv\Scripts\python server.py

echo.
echo Server stopped.
pause
exit /b 0

:fail
echo.
echo Setup failed - check that Python 3 is installed and on PATH.
pause
exit /b 1
