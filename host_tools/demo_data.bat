@echo off
title AFO Demo Data (fake Speedgoat)
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Run start_console.bat first to set up the Python environment.
  pause
  exit /b 1
)

rem Demo data arrives over UDP, which the console disables by default.
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 8321 -State Listen -ErrorAction SilentlyContinue){exit 1}else{exit 0}" >nul 2>&1
if errorlevel 1 (
  echo The console is already running. If it was NOT started with UDP enabled,
  echo close it first, then run this again ^(it will start the console correctly^).
) else (
  echo Starting the console with UDP demo input in a second window...
  start "AFO Rig Console" cmd /c start_console.bat --udp-port 5432
  timeout /t 3 >nul
)

echo.
echo   Streaming fake gait data to 127.0.0.1:5432
echo   Press Ctrl+C or close this window to stop.
echo   (Ignored automatically whenever real Speedgoat data is streaming.)
echo.
.venv\Scripts\python fake_speedgoat.py
echo.
echo Demo sender stopped.
pause
exit /b 0
