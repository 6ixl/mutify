# -*- coding: utf-8 -*-
"""MUTIFY — живой фильтр речи.

Запуск:  python main.py
         python main.py --tray   (свернуться в трей сразу, используется автозапуском)
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.branding import APP_NAME, ORG_NAME
from app.ui.icon import app_icon
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(app_icon())
    app.setFont(QFont("Segoe UI", 9))
    # Окно можно закрыть в трей — приложение при этом продолжает работать.
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow(start_in_tray="--tray" in sys.argv)
    if "--tray" not in sys.argv:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
