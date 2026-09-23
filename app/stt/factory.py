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


# Готовые режимы нагрузки: шаг проверки, окно анализа, вариантов расшифровки.
POWER_MODES = {
    "minimal": {
        "title": "Минимальная нагрузка",
        "hint": "Проверка раз в полсекунды, один вариант расшифровки. "
                "Процессор почти свободен, но мат будет проскакивать чаще.",
        "hop_ms": 500, "window_ms": 700, "alternatives": 1,
    },
    "economy": {
        "title": "Экономный",
        "hint": "Заметно легче обычного, качество чуть ниже.",
        "hop_ms": 350, "window_ms": 900, "alternatives": 2,
    },
    "balanced": {
        "title": "Обычный",
        "hint": "Баланс качества и нагрузки — примерно треть одного ядра.",
        "hop_ms": 250, "window_ms": 1000, "alternatives": 4,
    },
    "maximum": {
        "title": "Максимальное качество",
        "hint": "Самая частая проверка и самый глубокий разбор. "
                "Нагружает процессор постоянно, независимо от того, чем он занят.",
        "hop_ms": 100, "window_ms": 1600, "alternatives": 8,
    },
    "auto": {
        "title": "Автоматически",
        "hint": "Пока компьютер свободен — работает тщательнее, под нагрузкой "
                "сам отступает.",
        "hop_ms": 250, "window_ms": 1000, "alternatives": 4,
    },
}


def mode_values(cfg: AIConfig) -> tuple[int, int, int]:
    """Шаг, окно и число вариантов для текущего режима нагрузки."""
    preset = POWER_MODES.get(cfg.power_mode)
    if preset is None or cfg.power_mode == "manual":
        return cfg.hop_ms, cfg.window_ms, cfg.alternatives
    return preset["hop_ms"], preset["window_ms"], preset["alternatives"]


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
    hop_ms, window_ms, alternatives = mode_values(cfg)
    return VoskSTT(
        samplerate,
        model_path=cfg.model_path,
        threads=cfg.max_cpu_threads,
        react_on_partial=cfg.react_on_partial,
        window_ms=window_ms,
        hop_ms=hop_ms,
        skip_silence=cfg.skip_silence,
        silence_level_db=cfg.silence_level_db,
        normalize_quiet=cfg.normalize_quiet,
        alternatives=alternatives,
    )


def availability() -> dict[str, tuple[bool, str]]:
    return {name: cls.is_available() for name, cls in ENGINES.items()}
