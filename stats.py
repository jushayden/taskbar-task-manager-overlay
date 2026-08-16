"""System stats collection.

CPU/RAM -> psutil. GPU util / VRAM / GPU temp -> NVML (nvidia-ml-py).

Every source degrades independently: if one isn't available its fields stay None
and the widget renders '--' for them, so the app always runs.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import psutil

import config


@dataclass
class Reading:
    cpu: float | None = None          # %
    ram: float | None = None          # %
    ram_used: float | None = None     # GB
    ram_total: float | None = None    # GB
    disk: float | None = None         # % (activity or space, per config.DISK_MODE)
    store_used: float | None = None   # GB used on the system drive
    store_total: float | None = None  # GB total on the system drive
    gpu: float | None = None          # %
    vram_used: float | None = None    # GB
    vram_total: float | None = None   # GB
    gpu_temp: float | None = None     # °C


class _Nvml:
    """NVIDIA GPU util, VRAM and temperature via NVML.

    The handle is refreshed periodically: a long-lived NVML handle can start
    returning a stale utilization value (e.g. stuck at a game's peak after it
    exits) even though a fresh handle reads correctly, so we re-init on a timer
    and whenever a read fails.
    """

    REINIT_EVERY = 120  # seconds between forced NVML re-inits

    def __init__(self):
        self.nv = None
        self.h = None
        self._last_init = 0.0
        self._reinit()

    def _reinit(self) -> None:
        self._last_init = time.monotonic()
        try:
            import pynvml
            if self.nv is not None:
                try:
                    self.nv.nvmlShutdown()
                except Exception:
                    pass
            pynvml.nvmlInit()
            self.nv = pynvml
            self.h = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self.nv = None
            self.h = None

    def fill(self, r: Reading) -> None:
        if self.h is None or (time.monotonic() - self._last_init) >= self.REINIT_EVERY:
            self._reinit()
        if self.h is None:
            return
        nv = self.nv
        try:
            r.gpu = float(nv.nvmlDeviceGetUtilizationRates(self.h).gpu)
        except Exception:
            self.h = None  # broken handle -> re-init next cycle
            return
        try:
            m = nv.nvmlDeviceGetMemoryInfo(self.h)
            r.vram_used = m.used / 1024 ** 3
            r.vram_total = m.total / 1024 ** 3
        except Exception:
            pass
        try:
            r.gpu_temp = float(nv.nvmlDeviceGetTemperature(self.h, nv.NVML_TEMPERATURE_GPU))
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self.nv is not None:
                self.nv.nvmlShutdown()
        except Exception:
            pass


class Collector:
    def __init__(self):
        try:
            psutil.cpu_percent(interval=None)  # prime; first call returns 0.0
        except Exception:
            pass
        self._nvml = _Nvml()
        self._last_disk = None  # (busy_ms, monotonic_time)

    def _disk(self) -> float | None:
        if getattr(config, "DISK_MODE", "activity") == "space":
            try:
                return float(psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").percent)
            except Exception:
                return None
        # activity %: fraction of wall time the disk spent busy (approx, like Task Manager)
        try:
            io = psutil.disk_io_counters()
            if io is None:
                return None
            busy = getattr(io, "read_time", 0) + getattr(io, "write_time", 0)
            now = time.monotonic()
            if self._last_disk is None:
                self._last_disk = (busy, now)
                return 0.0
            pb, pt = self._last_disk
            self._last_disk = (busy, now)
            dt = (now - pt) * 1000.0
            if dt <= 0:
                return None
            return max(0.0, min(100.0, (busy - pb) / dt * 100.0))
        except Exception:
            return None

    def read(self) -> Reading:
        r = Reading()
        try:
            r.cpu = psutil.cpu_percent(interval=None)
        except Exception:
            pass
        try:
            vm = psutil.virtual_memory()
            r.ram = float(vm.percent)
            r.ram_used = vm.used / 1024 ** 3
            r.ram_total = vm.total / 1024 ** 3
        except Exception:
            pass
        r.disk = self._disk()
        try:
            du = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
            r.store_used = du.used / 1024 ** 3
            r.store_total = du.total / 1024 ** 3
        except Exception:
            pass
        self._nvml.fill(r)
        return r

    def close(self) -> None:
        self._nvml.close()


if __name__ == "__main__":  # quick manual check: python stats.py
    c = Collector()
    import time
    for _ in range(3):
        print(c.read())
        time.sleep(1)
    c.close()
