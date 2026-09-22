# -*- coding: utf-8 -*-
"""Приведение слова к канонической форме перед сравнением со словарём."""
from __future__ import annotations

import re

# Латиница и цифры, которыми маскируют русские буквы.
HOMOGLYPHS = {
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м",
    "o": "о", "p": "р", "t": "т", "x": "х", "y": "у", "u": "у", "i": "и",
    "n": "п", "r": "г", "s": "с", "z": "з", "g": "г", "d": "д", "l": "л",
    "f": "ф", "v": "в", "j": "й", "w": "ш", "q": "к",
    "0": "о", "1": "и", "3": "з", "4": "ч", "6": "б", "9": "я", "5": "б",
    "@": "а", "$": "с", "*": "", "_": "", "-": "", ".": "", "'": "",
}

_NON_LETTERS = re.compile(r"[^а-яё]")
_REPEATS = re.compile(r"(.)\1{1,}")


def normalize(word: str) -> str:
    """'Х-У-Й!!!' / 'xyu' / 'хууууй' -> 'хуй'."""
    word = word.strip().lower().replace("ё", "е").replace("ъ", "")
    word = "".join(HOMOGLYPHS.get(ch, ch) for ch in word)
    word = _NON_LETTERS.sub("", word)
    word = _REPEATS.sub(r"\1", word)
    return word


def normalize_keep_repeats(word: str) -> str:
    """То же, но без схлопывания повторов: «переебал» не должен стать «перебал»."""
    word = word.strip().lower().replace("ё", "е").replace("ъ", "")
    word = "".join(HOMOGLYPHS.get(ch, ch) for ch in word)
    return _NON_LETTERS.sub("", word)
