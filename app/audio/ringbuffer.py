# -*- coding: utf-8 -*-
"""Кольцевой буфер задержки.

Микрофон пишет сюда, вывод читает отсюда с отставанием на delay_ms.
Именно эта фора позволяет вырезать слово, которое уже прозвучало в микрофон,
но ещё не ушло собеседнику.
"""
from __future__ import annotations

import threading

import numpy as np


class DelayRing:
    def __init__(self, samplerate: int, capacity_ms: int = 4000) -> None:
        self.samplerate = samplerate
        self.capacity = max(1024, int(samplerate * capacity_ms / 1000))
        self._buf = np.zeros(self.capacity, dtype=np.float32)
        self._lock = threading.Lock()
        self.write_pos = 0          # всего записано сэмплов с начала сессии
        self.read_pos = 0           # всего выдано сэмплов

    # ---------- запись со стороны микрофона ----------
    def write(self, data: np.ndarray) -> None:
        n = len(data)
        if n == 0:
            return
        with self._lock:
            start = self.write_pos % self.capacity
            end = start + n
            if end <= self.capacity:
                self._buf[start:end] = data
            else:
                split = self.capacity - start
                self._buf[start:] = data[:split]
                self._buf[: end - self.capacity] = data[split:]
            self.write_pos += n

    # ---------- чтение со стороны вывода ----------
    def read(self, n: int, delay_samples: int) -> tuple[np.ndarray, int]:
        """Возвращает n сэмплов и абсолютную позицию их первого сэмпла.

        Позиция нужна, чтобы сопоставить звук с таймингами слов от модели.
        """
        with self._lock:
            target = self.write_pos - delay_samples
            # Дрейф часов между двумя звуковыми картами: мягко подтягиваем указатель.
            drift = target - self.read_pos
            if drift > self.samplerate // 10 or drift < -self.samplerate // 10:
                self.read_pos = target
            elif drift > n:
                self.read_pos += 1      # выход отстал — чуть ускоряемся
            elif drift < -n:
                self.read_pos -= 1      # выход убежал вперёд — притормаживаем

            pos = self.read_pos
            # В первые delay_ms читать ещё нечего: отдаём тишину, но указатель
            # двигаем как обычно, иначе поток никогда не догонит запись.
            if pos < 0 or pos + n > self.write_pos:
                self.read_pos = pos + n
                return np.zeros(n, dtype=np.float32), pos

            start = pos % self.capacity
            end = start + n
            if end <= self.capacity:
                out = self._buf[start:end].copy()
            else:
                split = self.capacity - start
                out = np.concatenate(
                    (self._buf[start:].copy(), self._buf[: end - self.capacity].copy())
                )
            self.read_pos += n
            return out, pos

    def reset(self) -> None:
        with self._lock:
            self._buf.fill(0.0)
            self.write_pos = 0
            self.read_pos = 0
