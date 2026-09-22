# -*- coding: utf-8 -*-
"""Скачивание и распаковка моделей Vosk прямо из приложения."""
from __future__ import annotations

import shutil
import urllib.request
import zipfile

from PySide6.QtCore import QThread, Signal

from app.paths import MODELS_DIR

CATALOG = {
    "vosk-model-small-ru-0.22": {
        "title": "Русская малая (45 МБ)",
        "hint": "Рекомендуется для живого мута: задержка 200-300 мс, работает на процессоре.",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
        "size_mb": 45,
    },
    "vosk-model-ru-0.42": {
        "title": "Русская большая (1.8 ГБ)",
        "hint": "Заметно точнее на быстрой речи. Требует ~4 ГБ оперативной памяти.",
        "url": "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
        "size_mb": 1800,
    },
}


class ModelDownloader(QThread):
    progress = Signal(int, str)      # проценты, текст состояния
    finished_ok = Signal(str)        # путь к распакованной модели
    failed = Signal(str)

    def __init__(self, model_key: str, parent=None) -> None:
        super().__init__(parent)
        self.model_key = model_key
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        entry = CATALOG.get(self.model_key)
        if entry is None:
            self.failed.emit("Неизвестная модель")
            return

        archive = MODELS_DIR / f"{self.model_key}.zip"
        target = MODELS_DIR / self.model_key
        if target.exists() and (target / "am").exists():
            self.finished_ok.emit(str(target))
            return

        try:
            self.progress.emit(0, "Соединение с сервером...")
            with urllib.request.urlopen(entry["url"], timeout=30) as response:
                total = int(response.headers.get("Content-Length", 0))
                done = 0
                with open(archive, "wb") as fh:
                    while True:
                        if self._cancelled:
                            self.failed.emit("Загрузка отменена")
                            return
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            percent = int(done * 92 / total)
                            self.progress.emit(
                                percent,
                                f"Загрузка... {done // 1048576} из {total // 1048576} МБ",
                            )
                        else:
                            self.progress.emit(50, f"Загрузка... {done // 1048576} МБ")

            self.progress.emit(94, "Распаковка...")
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(MODELS_DIR)
            archive.unlink(missing_ok=True)

            if not (target / "am").exists():
                found = self._find_extracted()
                if found is None:
                    self.failed.emit("В архиве не нашлась модель")
                    return
                if found != target:
                    if target.exists():
                        shutil.rmtree(target, ignore_errors=True)
                    found.rename(target)

            self.progress.emit(100, "Готово")
            self.finished_ok.emit(str(target))
        except Exception as exc:
            archive.unlink(missing_ok=True)
            self.failed.emit(str(exc))

    def _find_extracted(self):
        for child in MODELS_DIR.iterdir():
            if child.is_dir() and (child / "am").exists():
                return child
        return None
