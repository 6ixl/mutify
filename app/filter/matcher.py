# -*- coding: utf-8 -*-
"""Решает, является ли распознанное слово матом.

Четыре уровня проверки, часть из них отключается в настройках ИИ:
  1. белый список — обычные слова, похожие на мат, пропускаем сразу;
  2. точное совпадение со словарём;
  3. совпадение по корню — корень должен стоять в начале слова или после
     настоящей приставки, иначе «небеса» ловилось бы на корень «ебе»;
  4. нечёткое совпадение — ловит ошибки распознавания вроде «пиздетс».
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.config import AIConfig
from app.filter.normalizer import normalize, normalize_keep_repeats
from app.filter.wordlist import WordList

# Русские глагольные и именные приставки. Корень, стоящий сразу после любой их
# цепочки, считается настоящим: «за-ебал», «пере-рас-пиздить».
PREFIXES = (
    "недо", "пере", "пред", "через", "около",
    "без", "бес", "вне", "воз", "вос", "выс", "изо", "над", "обо", "ото",
    "вы", "со", "во", "ко", "по",
    "под", "подо", "при", "про", "раз", "рас", "разо", "роз", "рос", "сверх",
    "меж", "низ", "нис", "предо",
    "вз", "вс", "до", "за", "из", "ис", "на", "не", "ни", "об", "от", "по",
    "уж", "съ", "въ", "въе",
    "в", "у", "с", "о", "и", "а", "я",
)
# Отсортированы от длинных к коротким: длинную приставку пробуем первой.
_PREFIXES = tuple(sorted(set(PREFIXES), key=len, reverse=True))

MAX_PREFIX_CHAIN = 3


class Match:
    __slots__ = ("word", "rule", "score")

    def __init__(self, word: str, rule: str, score: float) -> None:
        self.word = word
        self.rule = rule
        self.score = score

    def __repr__(self) -> str:
        return f"<Match {self.word!r} via {self.rule} {self.score:.2f}>"


def prefix_is_real(prefix: str, depth: int = 0) -> bool:
    """Разбирается ли кусок слова перед корнем на настоящие приставки."""
    if not prefix:
        return True
    if depth >= MAX_PREFIX_CHAIN:
        return False
    for candidate in _PREFIXES:
        if prefix.startswith(candidate):
            if prefix_is_real(prefix[len(candidate):], depth + 1):
                return True
    return False


class ProfanityMatcher:
    def __init__(self, wordlist: WordList, ai: AIConfig) -> None:
        self.wordlist = wordlist
        self.ai = ai
        self._cache: dict[str, Match | None] = {}
        self.refresh()

    def refresh(self) -> None:
        """Пересобрать индексы после правки словаря или настроек."""
        # Словарные образцы нормализуем БЕЗ схлопывания повторов: иначе корень
        # «ссан» превращался в «сан» и глушил «санаторий», «осанку», «Ниссан»,
        # а «зассы» — в «засы» и глушил «засыпать». Растянутые буквы в речи
        # («хууууй») по-прежнему схлопываются у самого слова.
        def clean(word: str) -> str:
            return normalize_keep_repeats(word)

        self._roots = tuple(sorted(
            {clean(w) for w in self.wordlist.active_roots() if len(clean(w)) >= 3},
            key=len,
            reverse=True,
        ))
        self._exact = {clean(w) for w in self.wordlist.active_exact()
                       if len(clean(w)) >= 3}
        # Короткие слова вроде «ёб» проверяются только на полное совпадение:
        # корнем или нечётким сравнением двухбуквенное слово ловить нельзя.
        self._short = {clean(w) for w in self.wordlist.active_exact()
                       if len(clean(w)) == 2}
        # Исключения храним в обоих видах: слово проверяется и схлопнутым,
        # и целиком, иначе «вассал» проходил исключение в одной форме и
        # ловился корнем «ссал» в другой.
        self._allow = {form for w in self.wordlist.allow
                       for form in (normalize(w), clean(w)) if form}
        # Нечёткое сравнение только для длинных образцов: на коротких корнях
        # оно приняло бы «тебе» за мат.
        self._fuzzy_pool = tuple(
            w for w in (self._exact | set(self._roots)) if len(w) >= 5
        )
        self._cache.clear()

    # ---------- основной вход ----------
    def check(self, raw_word: str) -> Match | None:
        word = normalize(raw_word)
        if len(word) < 3:
            if word in self._short:
                return Match(raw_word, "exact", 1.0)
            return None

        cached = self._cache.get(word)
        if cached is not None or word in self._cache:
            return Match(raw_word, cached.rule, cached.score) if cached else None

        result = self._decide(word, raw_word)
        if result is None:
            # Схлопывание повторов могло съесть корень: «переебал» -> «перебал».
            full = normalize_keep_repeats(raw_word)
            if full != word and len(full) >= 3:
                result = self._decide(full, raw_word)
        if len(self._cache) > 4096:
            self._cache.clear()
        self._cache[word] = result
        return result

    def _decide(self, word: str, raw_word: str) -> Match | None:
        if word in self._allow:
            return None
        # Белый список работает и по вхождению: «застрахуйте» тоже пропускаем.
        for ok in self._allow:
            if len(ok) >= 5 and ok in word:
                return None

        if word in self._exact:
            return Match(raw_word, "exact", 1.0)

        if self.ai.root_matching:
            for root in self._roots:
                start = word.find(root)
                while start != -1:
                    if prefix_is_real(word[:start]):
                        return Match(raw_word, f"root:{root}", 0.95)
                    start = word.find(root, start + 1)

        if self.ai.fuzzy:
            best, best_score = None, 0.0
            for candidate in self._fuzzy_pool:
                if abs(len(candidate) - len(word)) > 3:
                    continue
                score = SequenceMatcher(None, word, candidate).ratio()
                if score > best_score:
                    best, best_score = candidate, score
            if best is not None and best_score >= self.ai.fuzzy_threshold:
                return Match(raw_word, f"fuzzy:{best}", best_score)

        return None

    def check_text(self, text: str) -> list[Match]:
        return [m for m in (self.check(w) for w in text.split()) if m is not None]
