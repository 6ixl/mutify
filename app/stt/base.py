# -*- coding: utf-8 -*-
"""Общий интерфейс движков распознавания речи."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    text: str
    start: float          # секунды от начала работы движка
    end: float
    conf: float = 1.0


@dataclass
class STTResult:
    words: list[Word] = field(default_factory=list)
    text: str = ""
    is_final: bool = False


class BaseSTT:
    """Движок получает сырой PCM и возвращает слова с таймингами."""

    name = "base"
    display_name = "Базовый"

    def __init__(self, samplerate: int) -> None:
        self.samplerate = samplerate

    def start(self) -> None:
        raise NotImplementedError

    def feed(self, pcm: bytes) -> list[STTResult]:
        raise NotImplementedError

    def flush(self) -> list[STTResult]:
        return []

    def stop(self) -> None:
        pass

    @staticmethod
    def is_available() -> tuple[bool, str]:
        return False, "не реализован"
