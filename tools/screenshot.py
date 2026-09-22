# -*- coding: utf-8 -*-
"""Снимок окна для проверки вёрстки без запуска настоящего приложения.

Запуск:  python tools/screenshot.py [ширина] [высота] [страница]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> None:
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1080
    height = int(sys.argv[2]) if len(sys.argv) > 2 else 780
    page = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    app = QApplication([])
    from app.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(width, height)
    window.show()
    window._go(page)
    for _ in range(8):
        app.processEvents()

    out = Path(os.environ.get("SHOT_DIR", ROOT)) / f"shot_{width}x{height}_{page}.png"
    window.grab().save(str(out), "PNG")
    print(out)


if __name__ == "__main__":
    main()
