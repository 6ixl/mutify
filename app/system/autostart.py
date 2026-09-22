# -*- coding: utf-8 -*-
"""Автозапуск вместе с Windows через ветку реестра Run текущего пользователя.

Прав администратора не требует: запись идёт в HKEY_CURRENT_USER.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.branding import APP_ID

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """Команда запуска: собранный .exe либо python с main.py."""
    exe = Path(sys.executable)
    if exe.name.lower() not in ("python.exe", "pythonw.exe"):
        return f'"{exe}"'
    # pythonw не показывает консольное окно при старте вместе с системой
    quiet = exe.with_name("pythonw.exe")
    runner = quiet if quiet.exists() else exe
    script = Path(__file__).resolve().parent.parent.parent / "main.py"
    return f'"{runner}" "{script}" --tray'


def is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_ID)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Включает или выключает автозапуск. Возвращает (получилось, сообщение)."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, _command())
                return True, "Приложение будет запускаться вместе с Windows"
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass
            return True, "Автозапуск выключен"
    except OSError as exc:
        return False, str(exc)
