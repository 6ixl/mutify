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


def selftest() -> int:
    """Проверка движков без окна: python main.py --selftest или Mutify.exe --selftest.

    Результат пишется в data/selftest.txt — у собранной программы нет консоли.
    """
    import time

    import numpy as np

    from app.paths import DATA_DIR

    lines = []
    for name in ("vosk", "whisper"):
        started = time.monotonic()
        try:
            if name == "vosk":
                from app.stt.vosk_engine import VoskSTT as Engine
                engine = Engine(16000)
            else:
                from app.stt.whisper_engine import WhisperSTT as Engine
                engine = Engine(16000, model="small")
            engine.start()
            device = getattr(engine, "used_device", "") or "cpu"
            engine.feed((np.zeros(16000, dtype=np.int16)).tobytes())
            lines.append(f"{name}: OK, устройство {device}, "
                         f"запуск {time.monotonic() - started:.1f} с")
            engine.stop()
        except Exception as exc:
            lines.append(f"{name}: ОШИБКА {exc}")
    (DATA_DIR / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
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
