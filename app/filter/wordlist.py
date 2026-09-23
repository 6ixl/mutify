# -*- coding: utf-8 -*-
"""Пользовательский словарь: корни, точные слова и белый список исключений."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.paths import WORDS_FILE
from app.filter import default_words


@dataclass
class WordList:
    roots: list[str] = field(default_factory=lambda: list(default_words.ROOTS))
    exact: list[str] = field(default_factory=lambda: list(default_words.EXACT))
    allow: list[str] = field(default_factory=lambda: list(default_words.ALLOW))
    # Мягкая брань лежит в словаре, но по умолчанию выключена галочкой.
    disabled: list[str] = field(
        default_factory=lambda: list(default_words.SOFT_OFF_BY_DEFAULT)
    )

    @classmethod
    def load(cls) -> "WordList":
        if not WORDS_FILE.exists():
            wl = cls()
            wl.offered = set(default_words.ROOTS + default_words.EXACT)
            wl.save()
            return wl
        try:
            raw = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return cls()
        words = cls(
            roots=raw.get("roots", list(default_words.ROOTS)),
            exact=raw.get("exact", list(default_words.EXACT)),
            allow=raw.get("allow", list(default_words.ALLOW)),
            disabled=raw.get("disabled", []),
        )
        # Какие стандартные слова уже предлагались этому пользователю. Нужно,
        # чтобы новые слова из обновления приехали, а удалённые им — нет.
        words.offered = set(raw.get("offered") or (
            words.roots + words.exact + words.allow + words.disabled
        ))
        words._migrate()
        return words

    # Корни, которые оказались опасными и цепляли обычные слова.
    RETIRED_ROOTS = ("шпили", "гомос", "блудн", "драчун")

    def _migrate(self) -> None:
        """Подтянуть сохранённый словарь к текущему стандартному.

        Иначе неудачный корень или недостающее исключение остались бы у тех,
        кто уже пользовался приложением.
        """
        changed = False
        for root in self.RETIRED_ROOTS:
            if root in self.roots:
                self.roots.remove(root)
                changed = True
        for word in default_words.ALLOW:
            if word not in self.allow:
                self.allow.append(word)
                changed = True

        # Новые слова из обновления словаря. То, что уже предлагалось раньше и
        # было удалено вручную, обратно не добавляем.
        offered = getattr(self, "offered", set())
        for bucket, defaults in ((self.roots, default_words.ROOTS),
                                 (self.exact, default_words.EXACT)):
            for word in defaults:
                if word in offered:
                    continue
                offered.add(word)
                if word not in bucket:
                    bucket.append(word)
                    changed = True
        # Слова, переведённые в «мягкую брань», выключаем один раз.
        for word in default_words.SOFT_OFF_BY_DEFAULT:
            marker = "soft:" + word
            if marker in offered:
                continue
            offered.add(marker)
            if word not in self.disabled and (word in self.roots or word in self.exact):
                self.disabled.append(word)
                changed = True
        self.offered = offered
        if changed:
            self.save()

    def save(self) -> None:
        WORDS_FILE.write_text(
            json.dumps(
                {
                    "roots": self.roots,
                    "exact": self.exact,
                    "allow": self.allow,
                    "disabled": self.disabled,
                    "offered": sorted(getattr(self, "offered", set())),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ---------- редактирование из UI ----------
    def add(self, kind: str, word: str) -> bool:
        word = word.strip().lower()
        if not word:
            return False
        bucket = getattr(self, kind)
        if word in bucket:
            return False
        bucket.append(word)
        self.save()
        return True

    def remove(self, kind: str, word: str) -> None:
        bucket = getattr(self, kind)
        if word in bucket:
            bucket.remove(word)
            self.save()

    def toggle(self, word: str, enabled: bool) -> None:
        if enabled and word in self.disabled:
            self.disabled.remove(word)
        elif not enabled and word not in self.disabled:
            self.disabled.append(word)
        self.save()

    def reset_defaults(self) -> None:
        self.roots = list(default_words.ROOTS)
        self.exact = list(default_words.EXACT)
        self.allow = list(default_words.ALLOW)
        self.disabled = list(default_words.SOFT_OFF_BY_DEFAULT)
        self.save()

    def active_roots(self) -> list[str]:
        return [w for w in self.roots if w not in self.disabled]

    def active_exact(self) -> list[str]:
        return [w for w in self.exact if w not in self.disabled]
