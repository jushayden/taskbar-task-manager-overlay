"""TaskbarStats — a compact always-on-top system monitor that snaps into the
empty right side of the Windows 11 taskbar. CPU/RAM/DISK/STORE/GPU/VRAM + GPU temp.

Run:  pythonw app.py
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

import config
from stats import Collector, Reading


# ---------------------------------------------------------------- win32 helpers
_user32 = ctypes.windll.user32
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetParent.restype = wintypes.HWND
_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]


def _rect(hwnd) -> wintypes.RECT | None:
    r = wintypes.RECT()
    if hwnd and _user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r
    return None


# ------------------------------------------------------------------- the widget
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QWidget  # noqa: E402

PAD_X = 6           # inner left/right padding
CELL_GAP = 10       # gap between cells
VALUE_PT = 10
TITLE_PT = 8
TEMP_PT = 8
METER_H = 3
ICON_SIZE = 14
ICON_GAP = 5        # gap between icon and title
TITLE_GAP = 5       # gap between title and value


def _color_load(v):
    if v is None:
        return config.MUTED
    return config.GOOD if v < config.LOAD_WARN else config.WARN if v < config.LOAD_CRIT else config.CRIT


def _color_temp(v):
    if v is None:
        return config.MUTED
    return config.GOOD if v < config.TEMP_WARN else config.WARN if v < config.TEMP_CRIT else config.CRIT


def _pct(v):
    return "--%" if v is None else f"{v:.0f}%"


def _degc(v):
    return "" if v is None else f" {v:.0f}°"


def _vram_text(r: Reading):
    if r.vram_used is None or r.vram_total is None:
        return "--"
    return f"{r.vram_used:.1f}/{r.vram_total:.0f}G"


def _vram_pct(r: Reading):
    if r.vram_used is None or r.vram_total in (None, 0):
        return None
    return r.vram_used / r.vram_total * 100


def _store_text(r: Reading):
    if r.store_used is None or r.store_total is None:
        return "--"
    if r.store_total >= 1000:  # TB for big drives -> more compact
        return f"{r.store_used / 1000:.1f}/{r.store_total / 1000:.1f}T"
    return f"{r.store_used:.0f}/{r.store_total:.0f}G"


def _store_pct(r: Reading):
    if r.store_used is None or r.store_total in (None, 0):
        return None
    return r.store_used / r.store_total * 100


# each cell: icon kind, value text, value color, optional temp, load% (for the meter), worst-case value
CELLS = [
    dict(icon="cpu", title="CPU", value=lambda r: _pct(r.cpu), color=lambda r: _color_load(r.cpu),
         temp=None, load=lambda r: r.cpu, worst="100%", has_temp=False),
    dict(icon="ram", title="RAM", value=lambda r: _pct(r.ram), color=lambda r: _color_load(r.ram),
         temp=None, load=lambda r: r.ram, worst="100%", has_temp=False),
    dict(icon="disk", title="DISK", value=lambda r: _pct(r.disk), color=lambda r: _color_load(r.disk),
         temp=None, load=lambda r: r.disk, worst="100%", has_temp=False),
    dict(icon="store", title="STORE", value=lambda r: _store_text(r), color=lambda r: _color_load(_store_pct(r)),
         temp=None, load=lambda r: _store_pct(r), worst="999/999G", has_temp=False),
    dict(icon="gpu", title="GPU", value=lambda r: _pct(r.gpu), color=lambda r: _color_load(r.gpu),
         temp=lambda r: r.gpu_temp, load=lambda r: r.gpu, worst="100%", has_temp=True),
    dict(icon="vram", title="VRAM", value=lambda r: _vram_text(r), color=lambda r: _color_load(_vram_pct(r)),
         temp=None, load=lambda r: _vram_pct(r), worst="88.8/88G", has_temp=False),
]


class StatsWidget(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.f_value = self._mono(VALUE_PT, QFont.DemiBold)
        self.f_title = self._mono(TITLE_PT, QFont.Medium)
        self.f_temp = self._mono(TEMP_PT, QFont.Medium)
        self.fm_value = QFontMetrics(self.f_value)
        self.fm_title = QFontMetrics(self.f_title)
        self.fm_temp = QFontMetrics(self.f_temp)

        # fixed cell widths (icon + title + value + worst-case temp) so digits never shift neighbours
        temp_w = self.fm_temp.horizontalAdvance(" 99°")
        for c in CELLS:
            vw = self.fm_value.horizontalAdvance(c["worst"]) + (temp_w if c["has_temp"] else 0)
            c["w"] = (ICON_SIZE + ICON_GAP + self.fm_title.horizontalAdvance(c["title"])
                      + TITLE_GAP + vw)

        total = PAD_X * 2 + sum(c["w"] for c in CELLS) + CELL_GAP * (len(CELLS) - 1)
        self.setFixedSize(int(total), config.HEIGHT)

        self._reading = Reading()
        self._collector = Collector()
        self._embedded = False
        self._parent = None
        self._shown = True
        self._hide_streak = 0

        # Collect stats on a background thread so a slow or stale sensor read can never
        # stall the refresh loop (a wedged read was leaving the displayed values pinned).
        try:
            self._reading = self._collector.read()
        except Exception:
            pass
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        self._tick = QTimer(self); self._tick.timeout.connect(self.update)
        self._tick.start(config.REFRESH_MS)
        self._pos = QTimer(self); self._pos.timeout.connect(self._reposition)
        self._pos.start(config.REPOSITION_MS)
        self._reposition()
        # extra early passes: at login the taskbar is still settling and an embedded child can
        # stay unpainted until the shell repaints — re-assert placement + force a paint a few times.
        for _delay in (600, 1500, 3000, 5000):
            QTimer.singleShot(_delay, self._reposition)

    def _mono(self, pt, weight):
        f = QFont(); f.setFamilies(config.MONO_FONTS); f.setPointSize(pt)
        f.setWeight(weight); f.setStyleHint(QFont.Monospace)
        return f

    # -- data + placement --
    def _read_loop(self):
        interval = max(0.2, config.REFRESH_MS / 1000.0)
        recreate_every = 60.0
        last_recreate = time.monotonic()
        while not self._stop.is_set():
            try:
                self._reading = self._collector.read()
            except Exception:
                pass
            # periodically rebuild the collector so a stale NVML/sensor handle can't pin values
            if time.monotonic() - last_recreate >= recreate_every:
                try:
                    fresh = Collector()
                    old, self._collector = self._collector, fresh
                    old.close()
                except Exception:
                    pass
                last_recreate = time.monotonic()
            self._stop.wait(interval)

    def _embed(self, hwnd, taskbar):
        """Reparent into the taskbar so Win11 can't composite over us (topmost isn't enough)."""
        GWL_STYLE, WS_CHILD, WS_POPUP = -16, 0x40000000, 0x80000000
        style = _user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
        style = (style & ~WS_POPUP) | WS_CHILD
        if style >= 0x80000000:
            style -= 0x100000000
        _user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        _user32.SetParent(hwnd, taskbar)
        self._parent = taskbar
        self._embedded = True

    def _app_edge(self, tb, scan_right_screen):
        """Rightmost screen-x with an app icon, scanning ONLY the taskbar strip left of the
        widget (so it can never detect itself). Pixel-based because the classic MSTask* window
        rect is stale on Win11. Detects icons by colour OR contrast vs the bar's own background,
        so it works on light *and* dark taskbars. None on failure -> skip collision handling."""
        try:
            img = QApplication.primaryScreen().grabWindow(
                0, tb.left, tb.top, tb.right - tb.left, tb.bottom - tb.top).toImage()
            w, h = img.width(), img.height()
            limit = max(0, min(w, scan_right_screen - tb.left))
            if limit <= 0:
                return None

            def lum(c):
                return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()

            # background = median luminance of the top row (empty bar even above an icon) -> theme-agnostic
            samples = [lum(img.pixelColor(sx, 2)) for sx in range(0, limit, max(1, limit // 24))]
            bg = sorted(samples)[len(samples) // 2] if samples else 0.0
            y0, y1 = int(h * 0.35), int(h * 0.70)
            rightmost = None
            for cx in range(0, limit, 3):
                for cy in range(y0, y1, 3):
                    c = img.pixelColor(cx, cy)
                    chroma = max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue())
                    if chroma > 45 or abs(lum(c) - bg) > 55:  # colourful, or high-contrast vs the bar
                        rightmost = cx
                        break
            return (tb.left + rightmost) if rightmost is not None else None
        except Exception:
            return None

    def _reposition(self):
        try:
            hwnd = int(self.winId())
            taskbar = _user32.FindWindowW("Shell_TrayWnd", None)
            if not taskbar:
                return
            if not self._embedded or self._parent != taskbar:
                self._embed(hwnd, taskbar)   # (re)attach — also recovers after an explorer restart
            tb = _rect(taskbar)
            tray = _rect(_user32.FindWindowExW(taskbar, None, "TrayNotifyWnd", None))
            if tb is None:
                return
            wr = _rect(hwnd)  # our REAL physical size (self.width() is logical -> wrong on HiDPI)
            phys_w = (wr.right - wr.left) if wr else self.width()
            phys_h = (wr.bottom - wr.top) if wr else self.height()
            tbh = tb.bottom - tb.top
            right_max = (tray.left if tray else tb.right) - config.TRAY_GAP  # widget right edge (screen)
            x_screen = right_max - phys_w                                    # flush against the tray
            y = int((tbh - phys_h) / 2)
            # apps only ever sit LEFT of us, so scan just left of the widget (never ourselves)
            app_edge = self._app_edge(tb, x_screen - 3)
            if app_edge is not None:
                need = app_edge + config.APP_GAP        # min left edge we need to avoid overlap
                if self._shown:
                    # only hide once it persists — ignores login/transient misreads (anti-disappear)
                    self._hide_streak = self._hide_streak + 1 if need > x_screen else 0
                    if self._hide_streak >= 2:
                        self._shown = False
                elif need + config.HIDE_HYST <= x_screen:  # clear room -> show again
                    self._shown = True
                    self._hide_streak = 0
            else:
                self._shown = True
                self._hide_streak = 0
            if not self._shown:
                _user32.ShowWindow(hwnd, 0)   # SW_HIDE — no room
                return
            _user32.ShowWindow(hwnd, 8)       # SW_SHOWNA (show without stealing focus)
            _user32.MoveWindow(hwnd, int(x_screen - tb.left), y, phys_w, phys_h, True)
            _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)  # HWND_TOP, NOMOVE|NOSIZE|NOACTIVATE
            _user32.RedrawWindow(hwnd, None, None, 0x105)  # force a paint (embedded child can stay blank)
        except Exception:
            pass

    # -- painting --
    def _icon(self, p, kind, x, y, s, color):
        """Draw a small monochrome vector glyph for the metric."""
        pen = QPen(QColor(color)); pen.setWidthF(1.3)
        pen.setJoinStyle(Qt.RoundJoin); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        if kind == "cpu":                     # chip: body + inner square + pins
            p.drawRoundedRect(QRectF(x + 3, y + 3, s - 6, s - 6), 2, 2)
            p.drawRoundedRect(QRectF(x + 5.5, y + 5.5, s - 11, s - 11), 1, 1)
            for i in range(3):
                px = x + 4.5 + i * (s - 9) / 2
                p.drawLine(QPointF(px, y + 1), QPointF(px, y + 3))
                p.drawLine(QPointF(px, y + s - 3), QPointF(px, y + s - 1))
                py = y + 4.5 + i * (s - 9) / 2
                p.drawLine(QPointF(x + 1, py), QPointF(x + 3, py))
                p.drawLine(QPointF(x + s - 3, py), QPointF(x + s - 1, py))
        elif kind == "ram":                   # memory stick: module + chip dividers + legs
            p.drawRoundedRect(QRectF(x + 1.5, y + 4, s - 3, s - 8), 1.5, 1.5)
            for i in (1, 2):
                lx = x + 1.5 + i * (s - 3) / 3
                p.drawLine(QPointF(lx, y + 6), QPointF(lx, y + s - 6))
            p.drawLine(QPointF(x + 4, y + s - 3), QPointF(x + 4, y + s - 1))
            p.drawLine(QPointF(x + s - 4, y + s - 3), QPointF(x + s - 4, y + s - 1))
        elif kind == "gpu":                   # card + fan + leg
            p.drawRoundedRect(QRectF(x + 1, y + 4.5, s - 2, s - 9), 1.5, 1.5)
            p.drawEllipse(QPointF(x + s / 2.0, y + s / 2.0), 2.4, 2.4)
            p.drawLine(QPointF(x + 3.5, y + s - 3), QPointF(x + 3.5, y + s - 1))
        elif kind == "vram":                  # stacked memory
            p.drawRoundedRect(QRectF(x + 2, y + 3, s - 8, s - 8), 1.5, 1.5)
            p.drawRoundedRect(QRectF(x + 5, y + 6, s - 8, s - 8), 1.5, 1.5)
        elif kind == "disk":                  # I/O activity waveform
            pts = [(x + 1.5, y + s / 2), (x + 4, y + 4), (x + 6.5, y + s - 4.5),
                   (x + 9, y + 5.5), (x + 11.5, y + s - 4), (x + s - 1.5, y + s / 2)]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))
        elif kind == "store":                 # storage cylinder
            p.drawEllipse(QRectF(x + 2.5, y + 2.5, s - 5, 4))
            p.drawLine(QPointF(x + 2.5, y + 4.5), QPointF(x + 2.5, y + s - 4.5))
            p.drawLine(QPointF(x + s - 2.5, y + 4.5), QPointF(x + s - 2.5, y + s - 4.5))
            p.drawArc(QRectF(x + 2.5, y + s - 6.5, s - 5, 4), 180 * 16, 180 * 16)
        else:
            p.drawEllipse(QRectF(x + 3, y + 3, s - 6, s - 6))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        # transparent background -> blends into the taskbar (no container box)

        r = self._reading
        vh = self.fm_value.height()
        value_top = 4
        icon_y = value_top + (vh - ICON_SIZE) / 2.0
        meter_y = self.height() - METER_H - 6
        x = PAD_X
        for c in CELLS:
            w = c["w"]
            self._icon(p, c["icon"], x, icon_y, ICON_SIZE, config.ICON)

            tx = x + ICON_SIZE + ICON_GAP
            title = c["title"]
            p.setFont(self.f_title); p.setPen(QColor(config.LABEL))
            p.drawText(int(tx), value_top, self.fm_title.horizontalAdvance(title) + 4, vh,
                       Qt.AlignLeft | Qt.AlignVCenter, title)

            vx = tx + self.fm_title.horizontalAdvance(title) + TITLE_GAP
            val = c["value"](r)
            p.setFont(self.f_value); p.setPen(QColor(c["color"](r)))
            p.drawText(int(vx), value_top, self.fm_value.horizontalAdvance(val) + 4, vh,
                       Qt.AlignLeft | Qt.AlignVCenter, val)
            if c["has_temp"]:
                ttext = _degc(c["temp"](r))
                if ttext:
                    ttx = vx + self.fm_value.horizontalAdvance(val)
                    p.setFont(self.f_temp); p.setPen(QColor(_color_temp(c["temp"](r))))
                    p.drawText(int(ttx), value_top, self.fm_temp.horizontalAdvance(ttext) + 4, vh,
                               Qt.AlignLeft | Qt.AlignVCenter, ttext)

            mx = x + ICON_SIZE + ICON_GAP
            mw = w - ICON_SIZE - ICON_GAP
            frac = max(0.0, min(1.0, (c["load"](r) or 0) / 100))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(config.TRACK))
            p.drawRoundedRect(QRectF(mx, meter_y, mw, METER_H), 1.5, 1.5)
            if frac > 0:
                p.setBrush(QColor(c["color"](r)))
                p.drawRoundedRect(QRectF(mx, meter_y, mw * frac, METER_H), 1.5, 1.5)

            x += w + CELL_GAP

    # -- interaction --
    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("Quit TaskbarStats", self._quit)
        m.exec(e.globalPos())

    def _quit(self):
        self._stop.set()
        try:
            self._collector.close()
        except Exception:
            pass
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = StatsWidget()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
