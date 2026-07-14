@echo off
rem Launch TaskbarStats (no console window). It self-elevates via UAC so CPU temp works.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "app.py"
