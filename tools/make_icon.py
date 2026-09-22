# -*- coding: utf-8 -*-
"""Пересобрать файлы иконки: assets/icon.png и assets/icon.ico.

Запуск:  python tools/make_icon.py
Нужен только при смене логотипа — само приложение рисует иконку на лету.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.icon import export_files  # noqa: E402


def main() -> None:
    QApplication([])
    png, ico = export_files()
    print("PNG:", png, os.path.getsize(png), "bytes")
    print("ICO:", ico, os.path.getsize(ico), "bytes")


if __name__ == "__main__":
    main()
