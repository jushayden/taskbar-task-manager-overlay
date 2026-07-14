"""Tunables for TaskbarStats. Edit these to taste."""

REFRESH_MS = 1000        # how often stats update (ms)
DISK_MODE = "activity"   # "activity" = Task-Manager-style busy %, "space" = used % of system drive
REPOSITION_MS = 2000     # how often we re-snap to the taskbar (ms)
TRAY_GAP = 14            # px gap kept to the left of the system tray/clock
APP_GAP = 12             # min gap kept from the app icons; auto-hide if the taskbar is too full
HIDE_HYST = 26           # once hidden, need this much extra clearance before showing again (anti-flicker)
HEIGHT = 40             # widget height in px (Win11 taskbar is ~48px)

# --- thresholds ---
LOAD_WARN, LOAD_CRIT = 70, 90    # % usage -> amber, red
TEMP_WARN, TEMP_CRIT = 70, 85    # °C -> amber, red

# --- palette (dark "OLED" system-utility look) ---
LABEL = "#94A3B8"          # muted slate-400 labels
ICON = "#8B98AD"           # icon stroke (muted)
TRACK = "#243044"          # meter track (subtle, reads on the taskbar)
GOOD = "#34D399"           # emerald-400 (softer than 500)
WARN = "#FBBF24"           # amber-400
CRIT = "#F87171"           # red-400
MUTED = "#64748B"          # for missing/'--' values

MONO_FONTS = ["Cascadia Mono", "Consolas"]  # first available wins
