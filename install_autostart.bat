@echo off
rem Run this AS ADMINISTRATOR once. Creates a logon task that starts TaskbarStats
rem elevated at every sign-in (so CPU temp works) with NO UAC prompt each time.
cd /d "%~dp0"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "APP=%~dp0app.py"

schtasks /Create /TN "TaskbarStats" /TR "\"%PYW%\" \"%APP%\" --no-elevate" /SC ONLOGON /RL HIGHEST /F
if not "%errorlevel%"=="0" (echo FAILED - run this file as Administrator. & timeout /t 5 /nobreak >nul & exit /b 1)

rem schtasks defaults the execution time limit to 3 days, which makes Task Scheduler
rem terminate an always-on app after 72h. Remove that limit (PT0S) and stop it
rem pausing on battery or when idle ends; add restart-on-failure for resilience.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1); $s.ExecutionTimeLimit = 'PT0S'; $s.IdleSettings.StopOnIdleEnd = $false; Set-ScheduledTask -TaskName 'TaskbarStats' -Settings $s | Out-Null"

rem (re)start it now so the overlay appears immediately, even when re-running to apply a fix.
schtasks /End /TN "TaskbarStats" >nul 2>&1
schtasks /Run /TN "TaskbarStats" >nul
echo Installed. TaskbarStats will start at logon (no time limit) and is running now.
timeout /t 5 /nobreak >nul
