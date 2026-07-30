@echo off
rem Fake Speedgoat - double-click to stream sample gait data into the console
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Run start_console.bat first to set up the Python environment.
  pause
  exit /b 1
)
echo Streaming fake gait data to 127.0.0.1:5432 - close this window to stop.
.venv\Scripts\python fake_speedgoat.py
