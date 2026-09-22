# -*- coding: utf-8 -*-
"""Пути приложения.

В обычном запуске всё лежит рядом с исходниками, в собранном .exe — рядом с
самим .exe. Так настройки, словарь, звуки и модель остаются на виду у
пользователя, а не прячутся внутри сборки.
"""
import sys
from pathlib import Path


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _root()

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"
MODELS_DIR = ROOT / "models"

CONFIG_FILE = DATA_DIR / "config.json"
WORDS_FILE = DATA_DIR / "words.json"

for _d in (DATA_DIR, ASSETS_DIR, SOUNDS_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
