@echo off
rem AFO web app: Home, Live, Trials, Run control, Teensy on http://<this PC>:8050
rem Uses the conda base Python. Close this window (or press Ctrl+C) to stop.
cd /d "%~dp0"
"C:\Users\Andy\miniconda3\python.exe" -u app.py
