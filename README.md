# Taskbar Task Manager

A compact, always-on-top system monitor that snaps into the empty space on the right
side of the Windows 11 taskbar. Shows **CPU %, RAM %, disk activity, storage, GPU %,
VRAM, and CPU/GPU temps** with green → amber → red threshold coloring.

## Run it
```
run.bat
```
It launches without a console window and asks for admin once (UAC) — admin is required so
LibreHardwareMonitor can read the **CPU temperature**. Everything else works without admin.

Right-click the widget → **Quit** to close it.

## Start automatically at login (recommended)
Right-click `install_autostart.bat` → **Run as administrator**. This registers a logon task
that starts the widget elevated every time you sign in — with **no UAC prompt** each time.
Remove it with `uninstall_autostart.bat`.

## Configure
Edit `config.py`:
- `LOAD_WARN/LOAD_CRIT`, `TEMP_WARN/TEMP_CRIT` — color thresholds
- `TRAY_GAP` — gap kept left of the clock/tray
- `REFRESH_MS` — update rate
- `DISK_MODE` — `"activity"` (Task-Manager-style busy %) or `"space"` (used % of system drive)
- `APP_GAP` / `HIDE_HYST` — spacing kept from the app icons; the widget auto-hides if the bar fills up
- palette colors

## Notes
- **GPU stats need an NVIDIA GPU** (uses NVML). On non-NVIDIA machines the GPU/VRAM/GPU-temp
  cells show `--`; CPU/RAM still work.
- **CPU temp needs admin** (LibreHardwareMonitor). Without elevation that cell shows `--`.
- Built for the **primary** Windows 11 taskbar.

## Stack
Python + PySide6. `stats.py` (psutil + NVML + LibreHardwareMonitor), `app.py` (the widget),
`config.py` (tunables), `lib/` (LibreHardwareMonitor net472 DLLs).

## Setup from scratch
```
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
(`lib/LibreHardwareMonitorLib.dll` + `HidSharp.dll` are the net472 build from
LibreHardwareMonitor v0.9.4.)
