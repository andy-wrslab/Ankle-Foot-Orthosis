@echo off
title AFO Demo Data (fake Speedgoat)
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Run start_console.bat first to set up the Python environment.
  pause
  exit /b 1
)
echo.
echo   Streaming fake gait data to 127.0.0.1:5432
echo   Press Ctrl+C or close this window to stop.
echo   (Ignored automatically whenever the real Speedgoat is streaming.)
echo.
.venv\Scripts\python fake_speedgoat.py
echo.
echo Demo sender stopped.
pause
exit /b 0
