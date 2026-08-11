"""System stats collection.

CPU/RAM -> psutil. GPU util / VRAM / GPU temp -> NVML (nvidia-ml-py).
CPU temp -> LibreHardwareMonitor via pythonnet (needs admin to read the sensor).

Every source degrades independently: if one isn't available its fields stay None
and the widget renders '--' for them, so the app always runs.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

import config

_LIB = Path(__file__).resolve().parent / "lib"


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
    cpu_temp: float | None = None     # °C
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


class _CpuTemp:
    """CPU package temperature via LibreHardwareMonitorLib (.NET, pythonnet)."""

    def __init__(self):
        self.computer = None
        self.HardwareType = None
        self.SensorType = None
        try:
            from pythonnet import load
            load("netfx")  # use .NET Framework 4.x (always present on Windows)
            import clr
            clr.AddReference(str(_LIB / "LibreHardwareMonitorLib.dll"))
            from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType
            self.HardwareType = HardwareType
            self.SensorType = SensorType
            c = Computer()
            c.IsCpuEnabled = True
            c.Open()
            self.computer = c
        except Exception:
            self.computer = None

    def read(self) -> float | None:
        if self.computer is None:
            return None
        try:
            best = None
            for hw in self.computer.Hardware:
                if hw.HardwareType != self.HardwareType.Cpu:
                    continue
                hw.Update()
                pkg, cores = None, []
                for s in hw.Sensors:
                    if s.SensorType != self.SensorType.Temperature or s.Value is None:
                        continue
                    name = s.Name or ""
                    val = float(s.Value)
                    if "Package" in name or "Tctl" in name or "Tdie" in name:
                        pkg = val
                    elif "Core" in name and "Max" not in name and "Average" not in name:
                        cores.append(val)
                if pkg is not None:
                    best = pkg
                elif cores:
                    best = max(cores)
            return best
        except Exception:
            return None

    def close(self) -> None:
        try:
            if self.computer is not None:
                self.computer.Close()
        except Exception:
            pass


class Collector:
    def __init__(self):
        try:
            psutil.cpu_percent(interval=None)  # prime; first call returns 0.0
        except Exception:
            pass
        self._nvml = _Nvml()
        self._cpu_temp = _CpuTemp()
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
        r.cpu_temp = self._cpu_temp.read()
        return r

    def close(self) -> None:
        self._nvml.close()
        self._cpu_temp.close()


if __name__ == "__main__":  # quick manual check: python stats.py
    c = Collector()
    import time
    for _ in range(3):
        print(c.read())
        time.sleep(1)
    c.close()
