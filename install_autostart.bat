@echo off
rem Run this AS ADMINISTRATOR once. Creates a logon task that starts TaskbarStats
rem elevated at every sign-in (so CPU temp works) with NO UAC prompt each time.
cd /d "%~dp0"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "APP=%~dp0app.py"
schtasks /Create /TN "TaskbarStats" /TR "\"%PYW%\" \"%APP%\" --no-elevate" /SC ONLOGON /RL HIGHEST /F
if %errorlevel%==0 (echo Installed. TaskbarStats will start at logon.) else (echo FAILED - run this file as Administrator.)
timeout /t 5 /nobreak >nul
