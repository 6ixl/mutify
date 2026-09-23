# -*- coding: utf-8 -*-
"""Сборка Mutify целиком: .exe плюс всё, что должно лежать рядом с ним.

    python tools/build.py

PyInstaller стирает dist/Mutify при каждой сборке, поэтому модель, звуки и
иконки копируются сюда после него — иначе собранная программа запускается без
модели и падает с «Failed to create a model».
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Mutify"


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "mutify.spec", "--noconfirm"],
        cwd=ROOT, check=True,
    )

    (DIST / "data").mkdir(parents=True, exist_ok=True)
    (DIST / "assets" / "sounds").mkdir(parents=True, exist_ok=True)
    (DIST / "models").mkdir(parents=True, exist_ok=True)

    for name in ("icon.png", "icon.ico"):
        source = ROOT / "assets" / name
        if source.exists():
            shutil.copy2(source, DIST / "assets" / name)

    sounds = ROOT / "assets" / "sounds"
    if sounds.exists():
        for item in sounds.iterdir():
            if item.is_file() and item.name != ".gitkeep":
                shutil.copy2(item, DIST / "assets" / "sounds" / item.name)

    copied = []
    models = ROOT / "models"
    if models.exists():
        for item in models.iterdir():
            if item.is_dir() and (item / "am").exists():
                target = DIST / "models" / item.name
                if not target.exists():
                    shutil.copytree(item, target)
                copied.append(item.name)

    print("Собрано:", DIST / "Mutify.exe")
    print("Модели рядом с программой:", ", ".join(copied) or "нет — скачайте из приложения")


if __name__ == "__main__":
    main()
