# -*- coding: utf-8 -*-
"""Расписание заглушений и источник подменного звука."""
from __future__ import annotations

import random
import threading
from collections import deque
from pathlib import Path

import numpy as np

from app.config import MuteConfig

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}
DECODED_MARK = ".decoded.wav"


class MuteSchedule:
    """Потокобезопасный список интервалов [start, end) в абсолютных сэмплах.

    Интервалы хранятся по отдельности, даже если они наслаиваются: каждое
    матерное слово — своё заглушение, и звук замены должен начинаться для
    него заново.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # [начало, конец, перезапускать ли звук]
        self._spans: list[list[int]] = []
        self.total_muted = 0        # статистика для UI
        self.events = 0

    def add(self, start: int, end: int, restart: bool = True) -> None:
        """restart=True — новое слово, звук замены начинается заново.

        restart=False — «мост» между двумя матами в быстрой речи: промежуток
        глушится, но звук не сбрасывается.
        """
        if end <= start:
            return
        with self._lock:
            kind = 1 if restart else 0
            for span in self._spans:
                # Повторная догадка модели про то же слово — просто продлеваем.
                # Слово с мостом не сливаем: иначе потеряется перезапуск звука.
                if span[2] == kind and abs(span[0] - start) < 1600 and start <= span[1]:
                    span[1] = max(span[1], end)
                    return
            self._spans.append([start, end, kind])
            if restart:
                self.events += 1

    def covers(self, pos: int, n: int) -> tuple[np.ndarray, list[int]] | None:
        """Маска заглушения для блока и позиции, где начинаются новые слова.

        Позиции стартов нужны, чтобы перезапустить звук замены: два мата
        подряд должны звучать как два отдельных сигнала, а не один тянущийся.
        """
        with self._lock:
            if not self._spans:
                return None
            self._spans = [s for s in self._spans if s[1] > pos - 48000]
            mask = np.zeros(n, dtype=bool)
            starts: list[int] = []
            hit = False
            for span in self._spans:
                start, end, restart = span[0], span[1], span[2]
                if end <= pos or start >= pos + n:
                    continue
                a = max(0, start - pos)
                b = min(n, end - pos)
                mask[a:b] = True
                hit = True
                if restart and pos <= start < pos + n:
                    starts.append(int(start - pos))
            if not hit:
                return None
            self.total_muted += int(mask.sum())
            return mask, sorted(starts)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


class ReplacementSound:
    """Звук, которым подменяется мат.

    Это может быть один файл, встроенный сигнал, тишина или целая библиотека —
    тогда на каждый мат берётся случайный звук из неё.
    """

    def __init__(self, samplerate: int) -> None:
        self.samplerate = samplerate
        self._clips: list[np.ndarray] = []
        self._data = np.zeros(0, dtype=np.float32)
        self._phase = 0
        self._queue: deque = deque()          # какие звуки прозвучат дальше
        self._last_index = -1
        self._lock = threading.Lock()
        self.source_name = "тишина"
        self.how = ""
        self.error = ""
        self.errors: list[str] = []

    # ------------------------------------------------------------ загрузка
    def load(self, cfg: MuteConfig) -> None:
        self._trim = bool(getattr(cfg, "trim_silence", True))
        self._limit = max(0, int(self.samplerate * getattr(cfg, "sound_length_ms", 0) / 1000))
        self._phase = 0
        self._queue.clear()
        self._last_index = -1
        self.error = ""
        self.errors = []
        self.how = ""

        if cfg.mode == "silence":
            self._clips = []
            self._data = np.zeros(0, dtype=np.float32)
            self.source_name = "тишина"
            return

        if cfg.mode == "random":
            self._load_library()
            return

        if cfg.mode == "beep" or not cfg.sound_path:
            self._data = self._shape(self._make_beep())
            self._clips = [self._data]
            self.source_name = "встроенный сигнал"
            return

        try:
            self._data, how = self._load_file(Path(cfg.sound_path))
            self._clips = [self._data]
            self.source_name = Path(cfg.sound_path).name
            self.how = how
        except Exception as exc:
            # Молча подменять бипом нельзя: человек будет думать, что поставил свой звук.
            self._data = self._shape(self._make_beep())
            self._clips = [self._data]
            self.source_name = "встроенный сигнал"
            self.error = str(exc)

    def _load_library(self) -> None:
        """Все звуки из папки: на каждый мат будет выбираться случайный."""
        from app.paths import SOUNDS_DIR

        clips: list[np.ndarray] = []
        names: list[str] = []
        for path in sorted(SOUNDS_DIR.iterdir()) if SOUNDS_DIR.exists() else []:
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            if path.name.endswith(DECODED_MARK):
                continue          # это кэш уже загруженного файла
            try:
                data, _ = self._load_file(path)
            except Exception as exc:
                self.errors.append(f"{path.name}: {exc}")
                continue
            if len(data):
                clips.append(data)
                names.append(path.name)

        if not clips:
            self._data = self._shape(self._make_beep())
            self._clips = [self._data]
            self.source_name = "встроенный сигнал"
            self.error = "в папке нет звуков, которые удалось прочитать"
            return

        self._clips = clips
        self._data = clips[0]
        self.source_name = f"случайный из {len(clips)}"
        self.how = ", ".join(names[:4]) + ("..." if len(names) > 4 else "")

    def _make_beep(self) -> np.ndarray:
        dur = 0.25
        t = np.linspace(0, dur, int(self.samplerate * dur), endpoint=False)
        tone = np.sin(2 * np.pi * 950 * t).astype(np.float32)
        env = np.minimum(1.0, np.minimum(t, dur - t) * 60).astype(np.float32)
        return tone * env * 0.6

    def _load_file(self, path: Path) -> tuple[np.ndarray, str]:
        from app.audio.decode import load_audio

        data, how = load_audio(path, self.samplerate)
        return self._shape(data), how

    def _shape(self, data: np.ndarray) -> np.ndarray:
        """Срезает тишину по краям и при необходимости укорачивает звук.

        Тишина в начале файла особенно вредна: при каждом новом мате вместо
        сигнала первые доли секунды звучала бы пустота, и казалось бы, что
        звук не начинается заново.
        """
        if len(data) == 0:
            return data

        if getattr(self, "_trim", True):
            threshold = max(1e-4, float(np.abs(data).max()) * 0.02)
            loud = np.flatnonzero(np.abs(data) >= threshold)
            if len(loud):
                start = int(loud[0])
                end = int(loud[-1]) + 1
                # немного воздуха по краям, чтобы не срезать атаку
                pad = int(self.samplerate * 0.005)
                data = data[max(0, start - pad):min(len(data), end + pad)]

        limit = getattr(self, "_limit", 0)
        if limit and len(data) > limit:
            data = data[:limit]
            # короткий спад, иначе обрез даст щелчок
            fade = min(len(data), int(self.samplerate * 0.01))
            if fade > 1:
                data = data.copy()
                data[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        return data

    # ------------------------------------------------------------ выбор
    def plan_next(self) -> int:
        """Заранее выбрать звук для следующего мата и вернуть его длину.

        Выбор делается здесь, а не в момент воспроизведения: движку нужно
        знать длину заранее, чтобы растянуть заглушение на весь звук.
        """
        with self._lock:
            if not self._clips:
                return 0
            index = 0
            if len(self._clips) > 1:
                index = random.randrange(len(self._clips))
                if index == self._last_index:      # два одинаковых подряд скучно
                    index = (index + 1) % len(self._clips)
            self._last_index = index
            self._queue.append(index)
            return len(self._clips[index])

    @property
    def length(self) -> int:
        """Длина текущего звука в сэмплах."""
        return len(self._data)

    @property
    def count(self) -> int:
        return len(self._clips)

    # ------------------------------------------------------------ звучание
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

    def render(self, n: int, starts: list[int], volume: float) -> np.ndarray:
        """Блок подменного звука, где на каждой позиции из starts он начинается заново.

        Благодаря этому два мата подряд звучат как два отдельных сигнала.
        """
        if not starts:
            return self.take(n, volume)

        out = np.empty(n, dtype=np.float32)
        cursor = 0
        for start in starts:
            start = max(0, min(n, start))
            if start > cursor:
                out[cursor:start] = self.take(start - cursor, volume)
            self.rewind()
            cursor = start
        if cursor < n:
            out[cursor:n] = self.take(n - cursor, volume)
        return out

    def rewind(self) -> None:
        """Начать звук сначала, взяв следующий запланированный клип."""
        with self._lock:
            if self._queue:
                index = self._queue.popleft()
                if 0 <= index < len(self._clips):
                    self._data = self._clips[index]
        self._phase = 0
