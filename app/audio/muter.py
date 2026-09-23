# -*- coding: utf-8 -*-
"""Расписание заглушений и источник подменного звука."""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from app.config import MuteConfig


class MuteSchedule:
    """Потокобезопасный список интервалов [start, end) в абсолютных сэмплах."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: list[list[int]] = []
        self.total_muted = 0        # статистика для UI
        self.events = 0

    def add(self, start: int, end: int) -> None:
        if end <= start:
            return
        with self._lock:
            # Склеиваем с соседним интервалом, если они пересекаются.
            for span in self._spans:
                if start <= span[1] and end >= span[0]:
                    span[0] = min(span[0], start)
                    span[1] = max(span[1], end)
                    return
            self._spans.append([start, end])
            self.events += 1

    def covers(self, pos: int, n: int) -> np.ndarray | None:
        """Маска длины n: True там, где сэмпл должен быть заглушён."""
        with self._lock:
            if not self._spans:
                return None
            self._spans = [s for s in self._spans if s[1] > pos - 48000]
            mask = np.zeros(n, dtype=bool)
            hit = False
            for start, end in self._spans:
                if end <= pos or start >= pos + n:
                    continue
                a = max(0, start - pos)
                b = min(n, end - pos)
                mask[a:b] = True
                hit = True
            if not hit:
                return None
            self.total_muted += int(mask.sum())
            return mask

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


class ReplacementSound:
    """Звук, которым подменяется мат. Свой файл, встроенный бип или тишина."""

    def __init__(self, samplerate: int) -> None:
        self.samplerate = samplerate
        self._data = np.zeros(0, dtype=np.float32)
        self._phase = 0
        self.source_name = "тишина"
        self.how = ""
        self.error = ""

    def load(self, cfg: MuteConfig) -> None:
        self._phase = 0
        self.error = ""
        if cfg.mode == "silence":
            self._data = np.zeros(0, dtype=np.float32)
            self.source_name = "тишина"
            return
        if cfg.mode == "beep" or not cfg.sound_path:
            self._data = self._make_beep()
            self.source_name = "встроенный сигнал"
            return
        try:
            self._data, how = self._load_file(Path(cfg.sound_path))
            self.source_name = Path(cfg.sound_path).name
            self.how = how
        except Exception as exc:
            # Молча подменять бипом нельзя: человек будет думать, что поставил свой звук.
            self._data = self._make_beep()
            self.source_name = "встроенный сигнал"
            self.error = str(exc)

    def _make_beep(self) -> np.ndarray:
        dur = 0.25
        t = np.linspace(0, dur, int(self.samplerate * dur), endpoint=False)
        tone = np.sin(2 * np.pi * 950 * t).astype(np.float32)
        env = np.minimum(1.0, np.minimum(t, dur - t) * 60).astype(np.float32)
        return tone * env * 0.6

    def _load_file(self, path: Path) -> tuple[np.ndarray, str]:
        from app.audio.decode import load_audio

        return load_audio(path, self.samplerate)

    def take(self, n: int, volume: float) -> np.ndarray:
        """Следующие n сэмплов подменного звука, зациклено."""
        if len(self._data) == 0:
            return np.zeros(n, dtype=np.float32)
        out = np.empty(n, dtype=np.float32)
        filled = 0
        while filled < n:
            chunk = min(n - filled, len(self._data) - self._phase)
            out[filled : filled + chunk] = self._data[self._phase : self._phase + chunk]
            self._phase = (self._phase + chunk) % len(self._data)
            filled += chunk
        return out * volume

    def rewind(self) -> None:
        self._phase = 0
