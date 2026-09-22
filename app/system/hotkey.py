# -*- coding: utf-8 -*-
"""Глобальная горячая клавиша Windows.

Обычный QShortcut срабатывает только когда окно в фокусе, а мут нужен прямо
во время игры или разговора. Здесь клавиша регистрируется в системе через
RegisterHotKey и ловится фильтром нативных сообщений Qt.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Понятные названия клавиш -> виртуальные коды Windows.
VK = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "PAUSE": 0x13, "SCROLL": 0x91, "INSERT": 0x2D, "DELETE": 0x2E,
    "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDN": 0x22,
    "NUM0": 0x60, "NUM1": 0x61, "NUM2": 0x62, "NUM3": 0x63, "NUM4": 0x64,
    "NUM5": 0x65, "NUM6": 0x66, "NUM7": 0x67, "NUM8": 0x68, "NUM9": 0x69,
    "`": 0xC0,
}
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    VK.setdefault(_ch, ord(_ch))

MODS = {
    "CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL,
    "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN,
}


def parse(combo: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+M' -> (модификаторы, код клавиши)."""
    mods, key = 0, None
    for part in combo.replace(" ", "").upper().split("+"):
        if not part:
            continue
        if part in MODS:
            mods |= MODS[part]
        else:
            key = VK.get(part)
    if key is None:
        return None
    return mods | MOD_NOREPEAT, key


class GlobalHotkey(QObject, QAbstractNativeEventFilter):
    """Регистрирует комбинации в системе и сообщает об их нажатии."""

    triggered = Signal(str)          # имя действия

    def __init__(self, parent=None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._by_id: dict[int, str] = {}
        self._next_id = 0xB100
        self._installed = False

    def install(self, app) -> None:
        if not self._installed:
            app.installNativeEventFilter(self)
            self._installed = True

    def register(self, action: str, combo: str) -> bool:
        parsed = parse(combo)
        if parsed is None:
            return False
        mods, key = parsed
        hotkey_id = self._next_id
        self._next_id += 1
        if not ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mods, key):
            return False           # комбинацию уже занял кто-то другой
        self._by_id[hotkey_id] = action
        return True

    def unregister_all(self) -> None:
        for hotkey_id in list(self._by_id):
            ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
        self._by_id.clear()

    # Qt отдаёт сюда все нативные сообщения потока.
    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                action = self._by_id.get(int(msg.wParam))
                if action:
                    self.triggered.emit(action)
        return False, 0
