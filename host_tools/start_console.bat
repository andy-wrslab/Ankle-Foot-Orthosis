@echo off
rem AFO Rig Console - double-click to start the server and open the dashboard
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo First run: creating the Python environment...
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
echo.
echo AFO Rig Console  -  http://localhost:8321
echo Close this window (or Ctrl+C) to stop the server.
echo.
start "" http://localhost:8321
.venv\Scripts\python server.py
