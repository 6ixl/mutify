# -*- coding: utf-8 -*-
"""Создание движка распознавания по настройкам."""
from __future__ import annotations

from app.config import AIConfig
from app.stt.base import BaseSTT
from app.stt.vosk_engine import VoskSTT
from app.stt.whisper_engine import WhisperSTT

ENGINES = {
    VoskSTT.name: VoskSTT,
    WhisperSTT.name: WhisperSTT,
}


def create(cfg: AIConfig, samplerate: int) -> BaseSTT:
    if cfg.engine == WhisperSTT.name:
        return WhisperSTT(
            samplerate,
            model=cfg.whisper_model,
            device=cfg.whisper_device,
            compute=cfg.whisper_compute,
            window_ms=cfg.whisper_window_ms,
            language=cfg.language,
        )
    return VoskSTT(
        samplerate,
        model_path=cfg.model_path,
        threads=cfg.max_cpu_threads,
        react_on_partial=cfg.react_on_partial,
        window_ms=cfg.window_ms,
        hop_ms=cfg.hop_ms,
        skip_silence=cfg.skip_silence,
    )


def availability() -> dict[str, tuple[bool, str]]:
    return {name: cls.is_available() for name, cls in ENGINES.items()}
