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
        "title": "Слабая — русская малая",
        "tier": "слабая",
        "accuracy": "точность средняя",
        "cost": "45 МБ · почти не грузит",
        "hint": "Мгновенная реакция и минимум нагрузки. На быстрой или "
                "невнятной речи иногда не разбирает слова.",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
        "size_mb": 45,
    },
    "vosk-model-ru-0.42": {
        "title": "Мощная — русская большая",
        "tier": "мощная",
        "accuracy": "точность высокая",
        "cost": "1.8 ГБ · тяжёлая для живого мута",
        "hint": "Хорошо слышит речь, но очень тяжёлая: грузится около полутора "
                "минут, а на обычном процессоре в живом режиме не успевает "
                "(замерено: 120–430% реального времени) — мат будет проходить. "
                "Для живого мута лучше Whisper на видеокарте.",
        "heavy": True,
        "url": "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
        "size_mb": 1847,
    },
    # --- Whisper: распознаёт заметно лучше, работает на видеокарте
    "whisper-small": {
        "title": "Средняя — Whisper small",
        "tier": "средняя",
        "kind": "whisper",
        "size": "small",
        "repo": "Systran/faster-whisper-small",
        "accuracy": "точность высокая",
        "cost": "480 МБ · видеокарта",
        "hint": "Заметно лучше Vosk на быстрой речи. На видеокарте один проход "
                "занимает около 0.1 с. Нужна задержка от 700 мс.",
        "size_mb": 480,
    },
    "whisper-medium": {
        "title": "Очень мощная — Whisper medium",
        "tier": "очень мощная",
        "kind": "whisper",
        "size": "medium",
        "repo": "Systran/faster-whisper-medium",
        "accuracy": "точность очень высокая",
        "cost": "1.5 ГБ · видеокарта от 4 ГБ",
        "hint": "Лучше всех разбирает невнятную и тихую речь. Проход дольше, "
                "задержку стоит поставить от 900 мс.",
        "size_mb": 1530,
    },
}

TIERS = ("слабая", "мощная", "средняя", "очень мощная")


def is_installed(key: str) -> bool:
    entry = CATALOG.get(key, {})
    folder = MODELS_DIR / key
    if entry.get("kind") == "whisper":
        return (folder / "model.bin").exists()
    return (folder / "am").exists()


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

        if entry.get("kind") == "whisper":
            self._download_whisper(entry)
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

    def _download_whisper(self, entry: dict) -> None:
        target = MODELS_DIR / self.model_key
        if (target / "model.bin").exists():
            self.finished_ok.emit(str(target))
            return
        try:
            from huggingface_hub import snapshot_download

            self.progress.emit(5, "Загрузка модели Whisper... это может занять время")
            snapshot_download(entry["repo"], local_dir=str(target))
            if not (target / "model.bin").exists():
                self.failed.emit("Модель скачалась не полностью")
                return
            self.progress.emit(100, "Готово")
            self.finished_ok.emit(str(target))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _find_extracted(self):
        for child in MODELS_DIR.iterdir():
            if child.is_dir() and (child / "am").exists():
                return child
        return None
