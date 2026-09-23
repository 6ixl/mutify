# -*- coding: utf-8 -*-
"""Профили настроек: готовые наборы под разные ситуации.

Профиль хранит только то, что относится к строгости фильтра и звуку замены.
Устройства и системные настройки в профиль не входят — они общие для всех.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from app.paths import DATA_DIR

PROFILES_FILE = DATA_DIR / "profiles.json"

# Какие поля попадают в профиль.
MUTE_FIELDS = (
    "delay_ms", "pre_pad_ms", "post_pad_ms", "mode", "sound_path",
    "sound_volume", "fade_ms", "burst_ms", "full_sound",
)
AI_FIELDS = (
    "engine", "hop_ms", "window_ms", "skip_silence", "react_on_partial",
    "confidence", "fuzzy", "fuzzy_threshold", "root_matching",
    "whisper_model", "whisper_window_ms",
)

BUILTIN: dict[str, dict[str, Any]] = {
    "Стрим": {
        "hint": "Максимальная строгость: лучше лишний раз заглушить, чем пропустить.",
        "mute": {"delay_ms": 600, "pre_pad_ms": 160, "post_pad_ms": 260,
                 "mode": "sound", "fade_ms": 15, "burst_ms": 900},
        "ai": {"hop_ms": 150, "window_ms": 1200, "react_on_partial": True, "confidence": 0.35,
               "fuzzy": True, "fuzzy_threshold": 0.78, "root_matching": True},
    },
    "Игра с друзьями": {
        "hint": "Баланс: разговор остаётся живым, мат режется надёжно.",
        "mute": {"delay_ms": 400, "pre_pad_ms": 120, "post_pad_ms": 180,
                 "mode": "sound", "fade_ms": 15, "burst_ms": 700},
        "ai": {"hop_ms": 250, "window_ms": 1000, "react_on_partial": True, "confidence": 0.55,
               "fuzzy": True, "fuzzy_threshold": 0.82, "root_matching": True},
    },
    "Работа": {
        "hint": "Минимальная задержка и только уверенные срабатывания.",
        "mute": {"delay_ms": 300, "pre_pad_ms": 90, "post_pad_ms": 140,
                 "mode": "silence", "fade_ms": 20, "burst_ms": 400},
        "ai": {"hop_ms": 300, "window_ms": 900, "react_on_partial": True, "confidence": 0.7,
               "fuzzy": False, "fuzzy_threshold": 0.88, "root_matching": True},
    },
}


def snapshot(cfg) -> dict[str, Any]:
    """Снять текущие настройки в профиль."""
    return {
        "mute": {f: getattr(cfg.mute, f) for f in MUTE_FIELDS},
        "ai": {f: getattr(cfg.ai, f) for f in AI_FIELDS},
    }


def apply(cfg, profile: dict[str, Any]) -> None:
    """Применить профиль к настройкам."""
    for field, value in (profile.get("mute") or {}).items():
        if field in MUTE_FIELDS:
            setattr(cfg.mute, field, value)
    for field, value in (profile.get("ai") or {}).items():
        if field in AI_FIELDS:
            setattr(cfg.ai, field, value)


def matches(cfg, profile: dict[str, Any]) -> bool:
    """Совпадают ли текущие настройки с профилем (звук не учитываем)."""
    current = snapshot(cfg)
    for section in ("mute", "ai"):
        for field, value in (profile.get(section) or {}).items():
            if field == "sound_path":
                continue
            if current[section].get(field) != value:
                return False
    return True


class ProfileStore:
    """Встроенные профили плюс сохранённые пользователем."""

    def __init__(self) -> None:
        self.custom: dict[str, dict[str, Any]] = {}
        self.active: str = "Игра с друзьями"
        self.load()

    # ------------------------------------------------------------ хранение
    def load(self) -> None:
        if not PROFILES_FILE.exists():
            return
        try:
            raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return
        self.custom = raw.get("custom", {})
        self.active = raw.get("active", self.active)

    def save(self) -> None:
        PROFILES_FILE.write_text(
            json.dumps({"custom": self.custom, "active": self.active},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # -------------------------------------------------------------- доступ
    def names(self) -> list[str]:
        return list(BUILTIN) + sorted(self.custom)

    def get(self, name: str) -> dict[str, Any] | None:
        if name in self.custom:
            return self.custom[name]
        return BUILTIN.get(name)

    def hint(self, name: str) -> str:
        profile = self.get(name) or {}
        return profile.get("hint", "Свой профиль.")

    def is_builtin(self, name: str) -> bool:
        return name in BUILTIN

    # ------------------------------------------------------------ действия
    def save_current(self, name: str, cfg, hint: str = "") -> None:
        """Сохранить текущие настройки под указанным именем."""
        data = snapshot(cfg)
        data["hint"] = hint or "Свой профиль."
        self.custom[name] = data
        self.active = name
        self.save()

    def apply_to(self, cfg, name: str) -> bool:
        """Применить профиль по имени и запомнить его как активный."""
        profile = self.get(name)
        if profile is None:
            return False
        apply(cfg, profile)
        self.active = name
        self.save()
        return True

    def remove(self, name: str) -> bool:
        if name in self.custom:
            del self.custom[name]
            if self.active == name:
                self.active = "Игра с друзьями"
            self.save()
            return True
        return False

    def detect(self, cfg) -> str | None:
        """Какому профилю соответствуют текущие настройки."""
        for name in self.names():
            profile = self.get(name)
            if profile and matches(cfg, profile):
                return name
        return None
