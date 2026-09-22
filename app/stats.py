# -*- coding: utf-8 -*-
"""Счётчик перехваченного мата: за сессию и за всё время."""
from __future__ import annotations

import json
import time
from collections import Counter

from app.paths import DATA_DIR

STATS_FILE = DATA_DIR / "stats.json"


class Stats:
    """Копит цифры и раз в несколько секунд сбрасывает их на диск."""

    SAVE_EVERY = 10.0

    def __init__(self) -> None:
        self.total_events = 0
        self.total_seconds = 0.0
        self.sessions = 0
        self.words: Counter = Counter()
        self.first_use = time.time()

        # счётчики текущего запуска
        self.session_events = 0
        self.session_seconds = 0.0
        self.session_start = time.time()

        self._last_save = 0.0
        self.load()

    # ------------------------------------------------------------ хранение
    def load(self) -> None:
        if not STATS_FILE.exists():
            return
        try:
            raw = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return
        self.total_events = int(raw.get("total_events", 0))
        self.total_seconds = float(raw.get("total_seconds", 0.0))
        self.sessions = int(raw.get("sessions", 0))
        self.words = Counter(raw.get("words", {}))
        self.first_use = float(raw.get("first_use", time.time()))

    def save(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_save < self.SAVE_EVERY:
            return
        self._last_save = now
        try:
            STATS_FILE.write_text(
                json.dumps(
                    {
                        "total_events": self.total_events,
                        "total_seconds": round(self.total_seconds, 2),
                        "sessions": self.sessions,
                        "first_use": self.first_use,
                        "last_use": now,
                        # храним только заметные слова, файл не должен пухнуть
                        "words": dict(self.words.most_common(200)),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------ действия
    def start_session(self) -> None:
        self.sessions += 1
        self.session_events = 0
        self.session_seconds = 0.0
        self.session_start = time.time()
        self.save(force=True)

    def add_word(self, word: str) -> None:
        self.total_events += 1
        self.session_events += 1
        cleaned = word.strip().lower()
        if cleaned:
            self.words[cleaned] += 1
        self.save()

    def set_session_seconds(self, seconds: float) -> None:
        """Движок присылает суммарную длительность заглушений за сессию."""
        delta = max(0.0, seconds - self.session_seconds)
        self.session_seconds = seconds
        self.total_seconds += delta
        self.save()

    def reset(self) -> None:
        self.total_events = 0
        self.total_seconds = 0.0
        self.sessions = 0
        self.words.clear()
        self.session_events = 0
        self.session_seconds = 0.0
        self.first_use = time.time()
        self.save(force=True)

    # ------------------------------------------------------------- справки
    def top_words(self, count: int = 5) -> list[tuple[str, int]]:
        return self.words.most_common(count)

    def since(self) -> str:
        days = max(0, int((time.time() - self.first_use) / 86400))
        if days == 0:
            return "сегодня"
        if days == 1:
            return "за вчера и сегодня"
        return f"за {days} дн."
