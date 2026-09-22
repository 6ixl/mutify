# -*- coding: utf-8 -*-
"""Автоматическая установка виртуального микрофона (VB-CABLE).

Приложение само скачивает официальный драйвер, распаковывает его и запускает
установщик. Windows спросит разрешение администратора — это обычное окно UAC,
без него драйвер поставить нельзя.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
import urllib.request
import zipfile
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QThread, Signal

DRIVER_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
SETUP_X64 = "VBCABLE_Setup_x64.exe"
SETUP_X86 = "VBCABLE_Setup.exe"

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NOASYNC = 0x00000100


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HANDLE),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def run_as_admin(exe: Path, params: str, show: int = 1, timeout_ms: int = 300000) -> int | None:
    """Запускает программу с правами администратора и ждёт её завершения.

    Возвращает код выхода, либо None, если пользователь отказал в UAC.
    """
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.hwnd = None
    info.lpVerb = "runas"
    info.lpFile = str(exe)
    info.lpParameters = params
    info.lpDirectory = str(exe.parent)
    info.nShow = show

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return None                      # отказ в UAC или запуск не состоялся
    if not info.hProcess:
        return None

    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, timeout_ms)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return int(code.value)


class CableInstaller(QThread):
    """Скачивает и ставит VB-CABLE в отдельном потоке."""

    progress = Signal(int, str)
    finished_ok = Signal(bool, str)      # нужна ли перезагрузка, сообщение
    failed = Signal(str)

    def __init__(self, silent: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.silent = silent
        self._workdir: Path | None = None

    def run(self) -> None:
        if os.name != "nt":
            self.failed.emit("Автоустановка доступна только в Windows")
            return
        try:
            folder = self._download_and_extract()
            setup = self._pick_setup(folder)
            self.progress.emit(55, "Запуск установщика, подтвердите запрос Windows...")

            # Недокументированные, но рабочие ключи тихой установки VB-CABLE.
            code = run_as_admin(setup, "-i -h" if self.silent else "")
            if code is None:
                self.failed.emit(
                    "Windows не дала прав администратора — без них драйвер не установить"
                )
                return

            self.progress.emit(85, "Проверка устройства...")
            from app.audio import devices

            devices.refresh_backend()
            cable = devices.find_virtual_cable()

            if cable is None and self.silent:
                # Тихий режим не сработал — показываем обычное окно установщика.
                self.progress.emit(
                    88, "Тихая установка не прошла, открываю обычный установщик..."
                )
                run_as_admin(setup, "")
                devices.refresh_backend()
                cable = devices.find_virtual_cable()

            self.progress.emit(100, "Готово")
            if cable is not None:
                self.finished_ok.emit(False, f"Виртуальный микрофон готов: {cable.name}")
            else:
                self.finished_ok.emit(
                    True,
                    "Драйвер установлен. Устройство появится после перезагрузки компьютера.",
                )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._cleanup()

    # ------------------------------------------------------------ загрузка
    def _download_and_extract(self) -> Path:
        self._workdir = Path(tempfile.mkdtemp(prefix="neonmute_cable_"))
        archive = self._workdir / "vbcable.zip"

        self.progress.emit(3, "Загрузка драйвера VB-CABLE...")
        with urllib.request.urlopen(DRIVER_URL, timeout=60) as response:
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            with open(archive, "wb") as fh:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    percent = int(done * 45 / total) + 3 if total else 25
                    self.progress.emit(min(48, percent), "Загрузка драйвера VB-CABLE...")

        self.progress.emit(50, "Распаковка...")
        target = self._workdir / "pack"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
        return target

    def _pick_setup(self, folder: Path) -> Path:
        name = SETUP_X64 if ctypes.sizeof(ctypes.c_void_p) == 8 else SETUP_X86
        setup = folder / name
        if not setup.exists():
            found = list(folder.rglob(name))
            if not found:
                raise FileNotFoundError("В архиве нет установщика " + name)
            setup = found[0]
        return setup

    def _cleanup(self) -> None:
        # Папку удаляем только после установки: установщик уже отработал.
        if self._workdir is not None:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None
