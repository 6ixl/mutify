# -*- coding: utf-8 -*-
"""Vosk: лёгкая офлайн-модель. Основной движок.

Работает скользящим окном, а не сплошным потоком. Это принципиально: в
потоковом режиме Vosk копит контекст и выдаёт первую гипотезу через 1.5-2
секунды после слова — к этому моменту звук уже ушёл бы собеседнику. Здесь
каждые hop_ms берётся последний кусок длиной window_ms, и у распознавателя
принудительно забирается результат, поэтому слово находится через 0.0-0.2 с
после того, как оно прозвучало.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from app.paths import MODELS_DIR
from app.stt.base import BaseSTT, STTResult, Word


class VoskSTT(BaseSTT):
    name = "vosk"
    display_name = "Vosk (быстрый, CPU)"

    def __init__(self, samplerate: int, model_path: str = "", threads: int = 4,
                 react_on_partial: bool = True, window_ms: int = 1000,
                 hop_ms: int = 250, skip_silence: bool = True) -> None:
        super().__init__(samplerate)
        self.model_path = model_path or self.autodetect_model()
        self.threads = threads
        self.react_on_partial = react_on_partial
        self.window = max(1, int(samplerate * window_ms / 1000))
        self.hop = max(1, int(samplerate * hop_ms / 1000))
        self.skip_silence = skip_silence
        self.silence_level = 0.004

        self._rec = None
        self._model = None
        self._buffer = np.zeros(0, dtype=np.int16)
        self._stream_pos = 0        # сколько сэмплов уже вышло из буфера
        self._since_last = 0        # сколько новых сэмплов с прошлой проверки
        self._fed = 0               # сколько сэмплов скормлено распознавателю
        self._seen: set = set()

    # ---------- поиск модели ----------
    @staticmethod
    def autodetect_model() -> str:
        """Ищет распакованную модель Vosk в папке models/."""
        if not MODELS_DIR.exists():
            return ""
        for child in sorted(MODELS_DIR.iterdir()):
            if child.is_dir() and (child / "am").exists():
                return str(child)
            if child.is_dir():
                for sub in child.iterdir():
                    if sub.is_dir() and (sub / "am").exists():
                        return str(sub)
        return ""

    @staticmethod
    def _looks_like_model(path: str) -> bool:
        """Похоже ли на распакованную модель Vosk: внутри должна быть папка am."""
        try:
            folder = Path(path)
            return folder.is_dir() and (folder / "am").exists()
        except OSError:
            return False

    @staticmethod
    def resolve_model_path(saved: str = "") -> str:
        """Какую модель использовать: своя папка models/ важнее сохранённого пути.

        Иначе установленная программа продолжала бы тянуть модель из папки, где
        её когда-то собирали, и ломалась, стоит той папке исчезнуть.
        """
        own = VoskSTT.autodetect_model()
        if own:
            return own
        if saved and VoskSTT._looks_like_model(saved):
            return saved
        return ""

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False, "пакет vosk не установлен (pip install vosk)"
        path = VoskSTT.autodetect_model()
        if not path:
            return False, "модель не найдена — нажмите «Скачать модель»"
        return True, os.path.basename(path)

    # ---------- жизненный цикл ----------
    def start(self) -> None:
        import vosk

        vosk.SetLogLevel(-1)

        # Папку могли перенести или удалить — тогда ищем модель заново.
        resolved = self.resolve_model_path(self.model_path)
        if resolved:
            self.model_path = resolved
        if not self.model_path:
            raise RuntimeError(
                "Модель не найдена. Откройте «Модель ИИ» и нажмите «Скачать модель»"
            )
        if not self._looks_like_model(self.model_path):
            raise RuntimeError(
                "Папка модели повреждена или это не модель Vosk: " + self.model_path
            )

        try:
            self._model = vosk.Model(self.model_path)
        except Exception as exc:
            raise RuntimeError(
                "Не удалось загрузить модель из " + self.model_path + " (" + str(exc) + ")"
            ) from exc
        self._rec = vosk.KaldiRecognizer(self._model, float(self.samplerate))
        self._rec.SetWords(True)
        self._buffer = np.zeros(0, dtype=np.int16)
        self._stream_pos = 0
        self._since_last = 0
        self._fed = 0
        self._seen.clear()

    def feed(self, pcm: bytes) -> list[STTResult]:
        if self._rec is None:
            return []
        chunk = np.frombuffer(pcm, dtype=np.int16)
        self._buffer = np.concatenate((self._buffer, chunk))

        results: list[STTResult] = []
        self._since_last += len(chunk)

        # Окно пересчитываем только когда накопился полный шаг новых данных,
        # иначе модель гоняется на каждый звуковой блок и ест процессор зря.
        while self._since_last >= self.hop:
            self._since_last -= self.hop

            end = len(self._buffer) - self._since_last
            start = max(0, end - self.window)
            window = self._buffer[start:end]
            if len(window) == 0:
                continue

            result = self._process(window, self._stream_pos + start)
            if result is not None:
                results.append(result)

        # В буфере держим ровно столько, сколько нужно следующему окну.
        keep = self.window + self._since_last
        if len(self._buffer) > keep:
            drop = len(self._buffer) - keep
            self._stream_pos += drop
            self._buffer = self._buffer[drop:]
        return results

    def _process(self, window: np.ndarray, window_start: int) -> STTResult | None:
        if self.skip_silence:
            level = float(np.sqrt(np.mean((window.astype(np.float32) / 32768.0) ** 2)))
            if level < self.silence_level:
                return None

        # Reset() не обнуляет внутренние часы распознавателя, поэтому время,
        # накопленное за прошлые окна, вычитаем сами.
        base = self._fed / self.samplerate
        self._rec.Reset()
        self._rec.AcceptWaveform(window.tobytes())
        self._fed += len(window)
        data = json.loads(self._rec.FinalResult())

        offset = window_start / self.samplerate
        words: list[Word] = []
        for item in data.get("result") or []:
            text = item.get("word", "")
            if not text:
                continue
            start = offset + (float(item.get("start", 0.0)) - base)
            end = offset + (float(item.get("end", 0.0)) - base)
            key = (text, round(start, 2))
            if key in self._seen:
                continue        # то же слово из предыдущего окна
            self._seen.add(key)
            if len(self._seen) > 512:
                self._seen.clear()
            words.append(
                Word(text=text, start=start, end=end,
                     conf=float(item.get("conf", 1.0)))
            )

        if not words:
            return None
        return STTResult(words=words, text=" ".join(w.text for w in words),
                         is_final=True)

    def flush(self) -> list[STTResult]:
        if self._rec is None or len(self._buffer) == 0:
            return []
        result = self._process(self._buffer, self._stream_pos)
        self._buffer = np.zeros(0, dtype=np.int16)
        return [result] if result is not None else []

    def stop(self) -> None:
        self._rec = None
        self._model = None
