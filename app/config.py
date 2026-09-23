"""Конфигурация приложения: загрузка, сохранение, значения по умолчанию."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

from app.paths import CONFIG_FILE


@dataclass
class AudioConfig:
    input_device: int | None = None      # индекс устройства ввода (микрофон)
    output_device: int | None = None     # индекс устройства вывода (VB-Cable Input)
    monitor_device: int | None = None    # опциональная прослушка в наушники
    monitor_enabled: bool = False
    samplerate: int = 16000              # Vosk работает на 16 кГц
    blocksize: int = 512                 # 32 мс при 16 кГц
    input_gain_db: float = 0.0
    output_gain_db: float = 0.0


@dataclass
class MuteConfig:
    delay_ms: int = 400                  # буфер упреждения: сколько звук держится перед выдачей
    pre_pad_ms: int = 120                # запас до начала слова
    post_pad_ms: int = 180               # запас после конца слова
    mode: str = "sound"                  # "sound" | "silence" | "beep"
    sound_path: str = ""                 # пользовательский wav/mp3 для замены
    sound_volume: float = 0.8
    fade_ms: int = 15                    # сглаживание на входе/выходе из мута, убирает щелчки
    hotkey_panic: bool = True            # мгновенный ручной мут по кнопке


@dataclass
class AIConfig:
    engine: str = "vosk"                 # "vosk" | "whisper"
    model_path: str = ""                 # путь к папке модели Vosk
    language: str = "ru"
    # --- скорость / глубина обдумывания ---
    hop_ms: int = 250                    # как часто проверяем речь
    window_ms: int = 1000                # сколько последних секунд слушает модель за раз
    skip_silence: bool = True            # не гонять модель по тишине — экономит процессор
    chunk_ms: int = 96                   # устаревшее, оставлено для старых настроек
    react_on_partial: bool = True        # реагировать на промежуточный результат (быстро)
    confidence: float = 0.55             # порог уверенности совпадения
    fuzzy: bool = True                   # ловить словоформы и опечатки распознавания
    fuzzy_threshold: float = 0.82        # схожесть для нечёткого совпадения
    root_matching: bool = True           # ловить по корню слова (матюки с приставками)
    lookahead_words: int = 1             # сколько слов держать перед решением
    max_cpu_threads: int = 4
    whisper_model: str = "small"         # tiny/base/small/medium/large-v3
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"
    whisper_window_ms: int = 900         # окно анализа для whisper


@dataclass
class UIConfig:
    accent: str = "#B14BFF"
    accent_2: str = "#7A2BFF"
    glow: bool = True
    start_minimized: bool = False


@dataclass
class GeneralConfig:
    autostart_mute: bool = False         # сразу включать мут при запуске программы
    minimize_to_tray: bool = True        # сворачивать в трей вместо панели задач
    close_to_tray: bool = True           # крестик прячет в трей, а не закрывает
    tray_notifications: bool = True      # всплывающие подсказки из трея
    hotkey_panic: str = "F8"             # мгновенная тишина
    hotkey_toggle: str = "Ctrl+Shift+M"  # включить/выключить мут
    hotkey_enabled: bool = True
    keep_history: bool = True            # вести журнал перехваченных слов
    history_limit: int = 500


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    mute: MuteConfig = field(default_factory=MuteConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)

    # ---------- persistence ----------
    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return cfg
            cfg._merge(raw)
        return cfg

    def _merge(self, raw: dict[str, Any]) -> None:
        for section in ("audio", "mute", "ai", "ui", "general"):
            values = raw.get(section) or {}
            target = getattr(self, section)
            for key, value in values.items():
                if hasattr(target, key):
                    setattr(target, key, value)

    def save(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
