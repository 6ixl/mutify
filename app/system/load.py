# -*- coding: utf-8 -*-
"""Загрузка компьютера: процессор и видеокарта.

Нужно, чтобы приложение само решало, можно ли работать тщательнее. Когда
машина простаивает, глупо экономить — лучше проверять речь чаще и точнее.
"""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import time
from ctypes import wintypes


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    @property
    def value(self) -> int:
        return (self.high << 32) | self.low


class SystemLoad:
    """Считает загрузку процессора между замерами и загрузку видеокарты."""

    def __init__(self) -> None:
        self._previous: tuple[int, int, int] | None = None
        self.cpu = 0.0              # 0..100
        self.gpu = 0.0              # 0..100, -1 если узнать нечем
        self._gpu_checked = 0.0
        self._gpu_tool = shutil.which("nvidia-smi")
        if self._gpu_tool is None:
            self.gpu = -1.0

    # ------------------------------------------------------------ процессор
    def _cpu_times(self) -> tuple[int, int, int] | None:
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        try:
            ok = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            )
        except Exception:
            return None
        if not ok:
            return None
        return idle.value, kernel.value, user.value

    def measure_cpu(self) -> float:
        """Средняя загрузка процессора с прошлого вызова."""
        now = self._cpu_times()
        if now is None:
            return self.cpu
        if self._previous is None:
            self._previous = now
            return self.cpu

        idle = now[0] - self._previous[0]
        # В kernel уже входит время простоя, поэтому вычитаем его.
        busy = (now[1] - self._previous[1]) + (now[2] - self._previous[2]) - idle
        total = busy + idle
        self._previous = now
        if total > 0:
            self.cpu = max(0.0, min(100.0, busy * 100.0 / total))
        return self.cpu

    # ----------------------------------------------------------- видеокарта
    def measure_gpu(self) -> float:
        """Загрузка видеокарты через nvidia-smi, не чаще раза в 5 секунд."""
        if self._gpu_tool is None:
            return -1.0
        now = time.monotonic()
        if now - self._gpu_checked < 5.0:
            return self.gpu
        self._gpu_checked = now
        try:
            result = subprocess.run(
                [self._gpu_tool, "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            line = result.stdout.decode("ascii", "ignore").strip().splitlines()[0]
            self.gpu = float(line.strip())
        except Exception:
            self.gpu = -1.0
            self._gpu_tool = None       # больше не дёргаем
        return self.gpu

    def measure(self) -> tuple[float, float]:
        return self.measure_cpu(), self.measure_gpu()

    @property
    def busiest(self) -> float:
        """Насколько занята машина в целом: берём худшее из двух."""
        return max(self.cpu, self.gpu if self.gpu >= 0 else 0.0)
