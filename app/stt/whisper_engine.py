# -*- coding: utf-8 -*-
"""faster-whisper: точнее Vosk, но работает окнами, поэтому задержка выше.

Имеет смысл при увеличенном буфере упреждения (от 800 мс) и на GPU.
"""
from __future__ import annotations

import numpy as np

from app.stt.base import BaseSTT, STTResult, Word


class WhisperSTT(BaseSTT):
    name = "whisper"
    display_name = "faster-whisper (точный, GPU)"

    def __init__(self, samplerate: int, model: str = "small", device: str = "cuda",
                 compute: str = "float16", window_ms: int = 900, language: str = "ru") -> None:
        super().__init__(samplerate)
        self.model_name = model
        self.device = device
        self.compute = compute
        self.window = int(samplerate * window_ms / 1000)
        self.overlap = int(samplerate * 0.2)
        self.language = language
        self._model = None
        self._buf = np.zeros(0, dtype=np.float32)
        self._base_time = 0.0

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "пакет faster-whisper не установлен (pip install faster-whisper)"
        return True, "готов"

    def start(self) -> None:
        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(self.model_name, device=self.device,
                                       compute_type=self.compute)
        except Exception:
            # Нет CUDA или неподходящий compute_type — откатываемся на процессор.
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            self.device = "cpu"
        self._buf = np.zeros(0, dtype=np.float32)
        self._base_time = 0.0

    def feed(self, pcm: bytes) -> list[STTResult]:
        if self._model is None:
            return []
        chunk = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate((self._buf, chunk))
        if len(self._buf) < self.window:
            return []
        audio = self._buf[: self.window]
        consumed = self.window - self.overlap
        self._buf = self._buf[consumed:]
        result = self._transcribe(audio, self._base_time)
        self._base_time += consumed / self.samplerate
        return [result] if (result.words or result.text) else []

    def flush(self) -> list[STTResult]:
        if self._model is None or len(self._buf) < self.samplerate * 0.2:
            return []
        result = self._transcribe(self._buf, self._base_time)
        self._buf = np.zeros(0, dtype=np.float32)
        return [result]

    def _transcribe(self, audio: np.ndarray, base: float) -> STTResult:
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        texts: list[str] = []
        for seg in segments:
            texts.append(seg.text.strip())
            for w in seg.words or []:
                words.append(
                    Word(
                        text=w.word.strip(),
                        start=base + float(w.start),
                        end=base + float(w.end),
                        conf=float(getattr(w, "probability", 1.0)),
                    )
                )
        return STTResult(words=words, text=" ".join(texts).strip(), is_final=True)

    def stop(self) -> None:
        self._model = None
