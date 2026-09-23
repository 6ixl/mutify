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
            is_model = (item / "am").exists() or (item / "model.bin").exists()
            if item.is_dir() and is_model:
                target = DIST / "models" / item.name
                if not target.exists():
                    shutil.copytree(item, target)
                copied.append(item.name)

    cuda = copy_cuda_libraries()

    print("Собрано:", DIST / "Mutify.exe")
    print("Библиотеки CUDA для Whisper:", cuda)
    print("Модели рядом с программой:", ", ".join(copied) or "нет — скачайте из приложения")


def copy_cuda_libraries() -> str:
    """cuBLAS и cuDNN из pip-пакетов nvidia-* кладутся в dist/Mutify/cuda.

    Без них Whisper в собранной программе работает только на процессоре.
    """
    import site

    target = DIST / "cuda"
    target.mkdir(exist_ok=True)
    count = 0
    for base in site.getsitepackages():
        nvidia = Path(base) / "nvidia"
        if not nvidia.is_dir():
            continue
        for dll in nvidia.glob("*/bin/*.dll"):
            if dll.name.startswith("nvblas"):
                continue            # не нужен ctranslate2
            destination = target / dll.name
            if not destination.exists() or destination.stat().st_size != dll.stat().st_size:
                shutil.copy2(dll, destination)
            count += 1
    return f"{count} файлов" if count else "не найдены — Whisper будет работать на процессоре"


if __name__ == "__main__":
    main()
