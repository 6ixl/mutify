# -*- coding: utf-8 -*-
"""faster-whisper: заметно точнее Vosk, особенно на быстрой и смазанной речи.

Работает тем же скользящим окном, что и Vosk: каждые hop_ms заново разбирается
последний кусок длиной window_ms. На видеокарте один проход малой модели
занимает десятки миллисекунд, так что слово находится почти сразу.

Модель берётся из папки models/whisper-<размер>, если она там есть, — тогда
интернет не нужен. Иначе faster-whisper скачает её сам при первом запуске.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from app.paths import MODELS_DIR
from app.stt.base import BaseSTT, STTResult, Word

# Подсказку со списком матерных слов пробовали: перехватов она не добавила,
# зато на чистой речи модель начинала «слышать» мат там, где его нет.
HOTWORDS = None

_DLL_DIRS_ADDED = False


def _expose_cuda_libraries() -> None:
    """Показать ctranslate2, где лежат cuBLAS и cuDNN из pip-пакетов nvidia-*.

    На Windows библиотеки ставятся в site-packages/nvidia/<пакет>/bin, и без
    явного указания пути модель не запустится на видеокарте.
    """
    global _DLL_DIRS_ADDED
    if _DLL_DIRS_ADDED or os.name != "nt":
        return
    _DLL_DIRS_ADDED = True

    candidates: list[Path] = []
    for base in sys.path:
        nvidia = Path(base) / "nvidia"
        if nvidia.is_dir():
            candidates.extend(p for p in nvidia.glob("*/bin") if p.is_dir())
    # в собранном .exe библиотеки лежат рядом с программой
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).resolve().parent / "cuda"
        if bundled.is_dir():
            candidates.append(bundled)

    for folder in candidates:
        try:
            os.add_dll_directory(str(folder))
        except (OSError, AttributeError):
            pass
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def local_model_path(size: str) -> str | None:
    """Папка со скачанной моделью Whisper, если она есть."""
    folder = MODELS_DIR / f"whisper-{size}"
    if (folder / "model.bin").exists():
        return str(folder)
    return None


def cuda_available() -> bool:
    _expose_cuda_libraries()
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperSTT(BaseSTT):
    name = "whisper"
    display_name = "faster-whisper (точный, видеокарта)"

    def __init__(self, samplerate: int, model: str = "small", device: str = "cuda",
                 compute: str = "float16", window_ms: int = 1500, language: str = "ru",
                 hop_ms: int = 300, skip_silence: bool = True,
                 silence_level_db: float = -58.0) -> None:
        super().__init__(samplerate)
        self.model_name = model
        self.device = device
        self.compute = compute
        self.language = language
        self.window = max(1, int(samplerate * window_ms / 1000))
        self.hop = max(1, int(samplerate * hop_ms / 1000))
        self.skip_silence = skip_silence
        self.silence_level = float(10.0 ** (silence_level_db / 20.0))

        self._model = None
        self._buffer = np.zeros(0, dtype=np.float32)
        self._stream_pos = 0
        self._since_last = 0
        self._seen: set = set()
        self.used_device = ""

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "пакет faster-whisper не установлен"
        where = "видеокарта" if cuda_available() else "процессор"
        return True, f"готов ({where})"

    # ------------------------------------------------------------ запуск
    def start(self) -> None:
        _expose_cuda_libraries()
        from faster_whisper import WhisperModel

        source = local_model_path(self.model_name) or self.model_name
        attempts = []
        if self.device == "cuda":
            attempts.append(("cuda", self.compute))
            attempts.append(("cuda", "int8_float16"))
        attempts.append(("cpu", "int8"))

        last_error = None
        for device, compute in attempts:
            try:
                self._model = WhisperModel(source, device=device, compute_type=compute)
                # пробный проход: на видеокарте ошибки всплывают только тут
                self._model.transcribe(
                    np.zeros(self.samplerate // 2, dtype=np.float32),
                    language=self.language, beam_size=1,
                )
                self.used_device = device
                break
            except Exception as exc:
                last_error = exc
                self._model = None
        if self._model is None:
            raise RuntimeError(f"Whisper не запустился: {last_error}")

        self._buffer = np.zeros(0, dtype=np.float32)
        self._stream_pos = 0
        self._since_last = 0
        self._seen.clear()

    def retune(self, hop_ms: int, window_ms: int, alternatives: int) -> None:
        self.hop = max(1, int(self.samplerate * hop_ms / 1000))
        self.window = max(1, int(self.samplerate * max(window_ms, 1000) / 1000))

    # ------------------------------------------------------------ звук
    def feed(self, pcm: bytes) -> list[STTResult]:
        if self._model is None:
            return []
        chunk = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer = np.concatenate((self._buffer, chunk))
        self._since_last += len(chunk)

        results: list[STTResult] = []
        while self._since_last >= self.hop:
            self._since_last -= self.hop
            end = len(self._buffer) - self._since_last
            start = max(0, end - self.window)
            window = self._buffer[start:end]
            if len(window):
                result = self._process(window, self._stream_pos + start)
                if result is not None:
                    results.append(result)

        keep = self.window + self._since_last
        if len(self._buffer) > keep:
            drop = len(self._buffer) - keep
            self._stream_pos += drop
            self._buffer = self._buffer[drop:]
        return results

    def _process(self, window: np.ndarray, window_start: int) -> STTResult | None:
        if self.skip_silence:
            level = float(np.sqrt(np.mean(window ** 2)))
            if level < self.silence_level:
                return None

        segments, _ = self._model.transcribe(
            window,
            language=self.language,
            beam_size=1,
            word_timestamps=True,
            vad_filter=False,               # тишину отсекаем сами, VAD режет короткие окна
            condition_on_previous_text=False,
            without_timestamps=False,
            hotwords=HOTWORDS,
            no_speech_threshold=0.6,
        )

        offset = window_start / self.samplerate
        words: list[Word] = []
        for segment in segments:
            for item in segment.words or []:
                text = item.word.strip(" .,!?;:«»\"'—-").lower()
                if not text:
                    continue
                start = offset + float(item.start)
                end = offset + float(item.end)
                key = (text, round(start, 1))
                if key in self._seen:
                    continue
                self._seen.add(key)
                if len(self._seen) > 512:
                    self._seen.clear()
                words.append(Word(text=text, start=start, end=end,
                                  conf=float(getattr(item, "probability", 1.0))))
        if not words:
            return None
        return STTResult(words=words, text=" ".join(w.text for w in words), is_final=True)

    def flush(self) -> list[STTResult]:
        if self._model is None or len(self._buffer) < self.samplerate // 5:
            return []
        result = self._process(self._buffer, self._stream_pos)
        self._buffer = np.zeros(0, dtype=np.float32)
        return [result] if result else []

    def stop(self) -> None:
        self._model = None
