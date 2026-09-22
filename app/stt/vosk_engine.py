# -*- coding: utf-8 -*-
"""Vosk: лёгкая офлайн-модель, задержка порядка 200-300 мс. Основной движок."""
from __future__ import annotations

import json
import os

from app.paths import MODELS_DIR
from app.stt.base import BaseSTT, STTResult, Word


class VoskSTT(BaseSTT):
    name = "vosk"
    display_name = "Vosk (быстрый, CPU)"

    def __init__(self, samplerate: int, model_path: str = "", threads: int = 4,
                 react_on_partial: bool = True) -> None:
        super().__init__(samplerate)
        self.model_path = model_path or self.autodetect_model()
        self.threads = threads
        self.react_on_partial = react_on_partial
        self._rec = None
        self._model = None
        self._last_partial = ""

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
    def is_available() -> tuple[bool, str]:
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False, "пакет vosk не установлен (pip install vosk)"
        path = VoskSTT.autodetect_model()
        if not path:
            return False, "модель не найдена — распакуйте её в папку models/"
        return True, os.path.basename(path)

    # ---------- жизненный цикл ----------
    def start(self) -> None:
        import vosk

        vosk.SetLogLevel(-1)
        if not self.model_path:
            raise RuntimeError("Не указана папка модели Vosk")
        self._model = vosk.Model(self.model_path)
        self._rec = vosk.KaldiRecognizer(self._model, float(self.samplerate))
        self._rec.SetWords(True)
        try:
            self._rec.SetPartialWords(True)
        except AttributeError:
            self.react_on_partial = False
        self._last_partial = ""

    def feed(self, pcm: bytes) -> list[STTResult]:
        if self._rec is None:
            return []
        out: list[STTResult] = []
        if self._rec.AcceptWaveform(pcm):
            data = json.loads(self._rec.Result())
            out.append(self._to_result(data, final=True))
            self._last_partial = ""
        elif self.react_on_partial:
            data = json.loads(self._rec.PartialResult())
            text = data.get("partial", "")
            if text and text != self._last_partial:
                self._last_partial = text
                out.append(self._to_result(data, final=False, key="partial"))
        return [r for r in out if r.text or r.words]

    def flush(self) -> list[STTResult]:
        if self._rec is None:
            return []
        data = json.loads(self._rec.FinalResult())
        return [self._to_result(data, final=True)]

    def stop(self) -> None:
        self._rec = None
        self._model = None

    # ---------- разбор ответа ----------
    def _to_result(self, data: dict, final: bool, key: str = "text") -> STTResult:
        words = []
        raw_words = data.get("result") if final else data.get("partial_result")
        for item in raw_words or []:
            words.append(
                Word(
                    text=item.get("word", ""),
                    start=float(item.get("start", 0.0)),
                    end=float(item.get("end", 0.0)),
                    conf=float(item.get("conf", 1.0)),
                )
            )
        return STTResult(words=words, text=data.get(key, ""), is_final=final)
