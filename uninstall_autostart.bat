@echo off
rem Removes the logon task created by install_autostart.bat.
schtasks /Delete /TN "TaskbarStats" /F
timeout /t 5 /nobreak >nul
