# -*- coding: utf-8 -*-
"""Аудио-конвейер.

    микрофон -> буфер задержки -> (вырезание мата) -> виртуальный кабель
                     |
                     +-> очередь -> поток распознавания -> расписание заглушений

Буфер задержки даёт фору: слово успевает распознаться до того, как этот же
кусок звука уйдёт собеседнику.
"""
from __future__ import annotations

import queue
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

from app.audio.devices import describe
from app.audio.muter import MuteSchedule, ReplacementSound
from app.audio.ringbuffer import DelayRing
from app.config import AppConfig
from app.filter.matcher import ProfanityMatcher
from app.stt import factory
from app.stt.base import STTResult


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


class AudioEngine(QObject):
    level_changed = Signal(float)              # уровень входа 0..1
    partial_text = Signal(str)                 # что модель слышит прямо сейчас
    final_text = Signal(str)
    profanity = Signal(str, str)               # слово, правило срабатывания
    mute_state = Signal(bool)                  # горит ли заглушение
    status = Signal(str, bool)                 # сообщение, успех/ошибка
    stats = Signal(int, float)                 # событий, секунд заглушено

    def __init__(self, cfg: AppConfig, matcher: ProfanityMatcher) -> None:
        super().__init__()
        self.cfg = cfg
        self.matcher = matcher
        self.running = False
        self.manual_mute = False

        self._ring: DelayRing | None = None
        self._schedule = MuteSchedule()
        self._sound: ReplacementSound | None = None
        self._stt = None
        self._stt_queue: queue.Queue = queue.Queue(maxsize=64)
        self._stt_thread: threading.Thread | None = None
        self._in_stream = None
        self._out_stream = None
        self._monitor_stream = None
        self._monitor_queue: queue.Queue = queue.Queue(maxsize=8)
        self._out_channels = 2

        self._fade_tail = np.zeros(0, dtype=np.float32)
        # Сколько сэмплов модель не увидела: её шкала времени сдвинута на это
        # число относительно позиции в кольцевом буфере.
        self._stt_offset = 0
        self.missed = 0
        self._gate_gain = 1.0
        self._last_mute_end = 0      # конец прошлого заглушения — для склейки серий
        self._last_level_emit = 0.0
        self._last_stats_emit = 0.0
        self._muting_now = False
        self._handled_words: set = set()

    # ------------------------------------------------------------------ запуск
    def start(self) -> bool:
        if self.running:
            return True
        import sounddevice as sd

        sr = self.cfg.audio.samplerate
        self._ring = DelayRing(sr, capacity_ms=max(4000, self.cfg.mute.delay_ms * 4))
        self._schedule = MuteSchedule()
        self._sound = ReplacementSound(sr)
        self._sound.load(self.cfg.mute)
        self._handled_words.clear()
        self._fade_tail = np.zeros(0, dtype=np.float32)
        self._stt_offset = 0
        self.missed = 0
        self._last_mute_end = 0

        try:
            self._stt = factory.create(self.cfg.ai, sr)
            self._stt.start()
        except Exception as exc:
            self.status.emit("Модель не запустилась: {}".format(exc), False)
            return False

        out_index = self.cfg.audio.output_device
        in_index = self.cfg.audio.input_device
        if out_index is None:
            self.status.emit("Не выбрано устройство вывода (VB-Cable)", False)
            return False

        try:
            self._out_channels = self._channels_for(out_index)
            self._in_stream = sd.InputStream(
                device=in_index,
                channels=1,
                samplerate=sr,
                blocksize=self.cfg.audio.blocksize,
                dtype="float32",
                callback=self._on_input,
                latency="low",
            )
            self._out_stream = sd.OutputStream(
                device=out_index,
                channels=self._out_channels,
                samplerate=sr,
                blocksize=self.cfg.audio.blocksize,
                dtype="float32",
                callback=self._on_output,
                latency="low",
            )
            self._in_stream.start()
            self._out_stream.start()
            if self.cfg.audio.monitor_enabled and self.cfg.audio.monitor_device is not None:
                self._start_monitor(sd)
        except Exception as exc:
            self.status.emit("Звуковое устройство недоступно: {}".format(exc), False)
            self.stop()
            return False

        self.running = True
        self._stt_thread = threading.Thread(target=self._stt_loop, daemon=True)
        self._stt_thread.start()
        self.status.emit(
            "Работает: {} -> {}".format(
                describe(in_index, "input"), describe(out_index, "output")
            ),
            True,
        )
        return True

    def _channels_for(self, index: int) -> int:
        import sounddevice as sd

        info = sd.query_devices(index)
        return 2 if info["max_output_channels"] >= 2 else 1

    def _start_monitor(self, sd) -> None:
        self._monitor_stream = sd.OutputStream(
            device=self.cfg.audio.monitor_device,
            channels=self._channels_for(self.cfg.audio.monitor_device),
            samplerate=self.cfg.audio.samplerate,
            blocksize=self.cfg.audio.blocksize,
            dtype="float32",
            callback=self._on_monitor,
            latency="low",
        )
        self._monitor_stream.start()

    # ------------------------------------------------------------------ стоп
    def stop(self) -> None:
        was_running = self.running
        self.running = False
        try:
            self._stt_queue.put_nowait(None)
        except queue.Full:
            pass
        for stream in (self._in_stream, self._out_stream, self._monitor_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._in_stream = self._out_stream = self._monitor_stream = None
        if self._stt_thread is not None:
            self._stt_thread.join(timeout=2.0)
            self._stt_thread = None
        if self._stt is not None:
            try:
                self._stt.stop()
            except Exception:
                pass
            self._stt = None
        self._muting_now = False
        self.mute_state.emit(False)
        if was_running:
            self.status.emit("Остановлено", True)

    # ------------------------------------------------------- callback: вход
    def _on_input(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0] * db_to_gain(self.cfg.audio.input_gain_db)
        if self._ring is not None:
            self._ring.write(mono)

        pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        try:
            self._stt_queue.put_nowait(pcm)
        except queue.Full:
            # Модель не успевает: кусок пропускаем, но помним, что её время
            # теперь отстаёт от потока ровно на эти сэмплы.
            self._stt_offset += frames

        now = time.monotonic()
        if now - self._last_level_emit > 0.05:
            self._last_level_emit = now
            self.level_changed.emit(float(np.sqrt(np.mean(mono ** 2)) * 3.0))

    # ------------------------------------------------------ callback: выход
    def _on_output(self, outdata, frames, time_info, status) -> None:
        if self._ring is None or self._sound is None:
            outdata.fill(0.0)
            return

        delay = int(self.cfg.audio.samplerate * self.cfg.mute.delay_ms / 1000)
        data, pos = self._ring.read(frames, delay)

        starts: list[int] = []
        if self.manual_mute:
            mask = np.ones(frames, dtype=bool)
        else:
            covered = self._schedule.covers(pos, frames)
            mask, starts = covered if covered is not None else (None, [])

        if mask is not None:
            env = self._smooth(mask.astype(np.float32))
            # На каждом новом слове звук замены начинается заново, поэтому два
            # мата подряд звучат как два сигнала, а не один тянущийся.
            replacement = self._sound.render(frames, starts, self.cfg.mute.sound_volume)
            data = data * (1.0 - env) + replacement * env
            active = bool(env.max() > 0.5)
        else:
            self._fade_tail = np.zeros(0, dtype=np.float32)
            self._sound.rewind()
            active = False

        if active != self._muting_now:
            self._muting_now = active
            self.mute_state.emit(active)

        if self.cfg.audio.noise_gate:
            data = self._apply_gate(data)

        data = np.clip(data * db_to_gain(self.cfg.audio.output_gain_db), -1.0, 1.0)
        outdata[:] = np.repeat(data[:, None], self._out_channels, axis=1)

        if self._monitor_stream is not None:
            try:
                self._monitor_queue.put_nowait(data.copy())
            except queue.Full:
                pass

        now = time.monotonic()
        if now - self._last_stats_emit > 0.5:
            self._last_stats_emit = now
            self.stats.emit(
                self._schedule.events,
                self._schedule.total_muted / self.cfg.audio.samplerate,
            )

    def _on_monitor(self, outdata, frames, time_info, status) -> None:
        try:
            data = self._monitor_queue.get_nowait()
        except queue.Empty:
            outdata.fill(0.0)
            return
        if len(data) < frames:
            data = np.pad(data, (0, frames - len(data)))
        outdata[:] = np.repeat(data[:frames, None], outdata.shape[1], axis=1)

    def _apply_gate(self, data: np.ndarray) -> np.ndarray:
        """Шумоподавление: приглушает паузы тише порога.

        Выключено по умолчанию — включается и настраивается на странице «Аудио».
        """
        level = float(np.sqrt(np.mean(data ** 2)))
        threshold = db_to_gain(self.cfg.audio.gate_threshold_db)
        target = 1.0 if level >= threshold else 0.0

        release = max(1, int(self.cfg.audio.samplerate
                             * self.cfg.audio.gate_release_ms / 1000))
        step = len(data) / release
        previous = self._gate_gain
        if target > previous:
            self._gate_gain = min(1.0, previous + step)
        elif target < previous:
            self._gate_gain = max(0.0, previous - step)

        if previous >= 0.999 and self._gate_gain >= 0.999:
            return data
        # Плавный переход внутри блока, иначе на границах слышны щелчки.
        ramp = np.linspace(previous, self._gate_gain, len(data), dtype=np.float32)
        return data * ramp

    # --------------------------------------------- сглаживание краёв заглушки
    def _smooth(self, env: np.ndarray) -> np.ndarray:
        """Убирает щелчки на входе и выходе из заглушения."""
        fade = max(2, int(self.cfg.audio.samplerate * self.cfg.mute.fade_ms / 1000))
        window = np.ones(fade, dtype=np.float32) / fade
        if len(self._fade_tail) == fade:
            tail = self._fade_tail
        else:
            tail = np.zeros(fade, dtype=np.float32)
        padded = np.concatenate((tail, env))
        smoothed = np.convolve(padded, window, mode="same")[len(tail):]
        if len(env) >= fade:
            self._fade_tail = env[-fade:].copy()
        else:
            self._fade_tail = env.copy()
        return np.clip(smoothed, 0.0, 1.0)

    # ------------------------------------------------- поток распознавания
    def _stt_loop(self) -> None:
        while self.running:
            try:
                pcm = self._stt_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if pcm is None:
                break
            try:
                results = self._stt.feed(pcm)
            except Exception as exc:
                self.status.emit("Ошибка распознавания: {}".format(exc), False)
                continue
            for result in results:
                self._handle_result(result)

    def _handle_result(self, result: STTResult) -> None:
        if result.text:
            if result.is_final:
                self.final_text.emit(result.text)
            else:
                self.partial_text.emit(result.text)

        sr = self.cfg.audio.samplerate
        pre = int(sr * self.cfg.mute.pre_pad_ms / 1000)
        post = int(sr * self.cfg.mute.post_pad_ms / 1000)

        for word in result.words:
            if result.is_final and word.conf < self.cfg.ai.confidence:
                continue
            key = (word.text, int(word.start * 100))
            if key in self._handled_words:
                continue
            match = self.matcher.check(word.text)
            if match is None:
                continue
            self._handled_words.add(key)
            if len(self._handled_words) > 512:
                self._handled_words.clear()

            # Время модели переводим в позицию потока: у неё своя шкала.
            start = max(0, int(word.start * sr) + self._stt_offset - pre)
            end = int(word.end * sr) + self._stt_offset + post

            # Звук для этого слова выбирается заранее: в случайном режиме нужно
            # знать, какой именно клип прозвучит, чтобы растянуть заглушение
            # ровно на его длину.
            if self._sound is not None and self.cfg.mute.mode != "silence":
                planned = self._sound.plan_next()
                if self.cfg.mute.full_sound and planned:
                    fade = int(sr * self.cfg.mute.fade_ms / 1000)
                    end = max(end, start + planned + fade)

            # Быстрая речь: модель успевает разобрать не каждое слово в потоке
            # мата. Если новый мат идёт вплотную к прошлому, глушим и промежуток
            # между ними — иначе в эфир просочится то, что модель не расслышала.
            burst = int(sr * self.cfg.mute.burst_ms / 1000)
            if 0 < self._last_mute_end <= start <= self._last_mute_end + burst:
                self._schedule.add(self._last_mute_end, start, restart=False)
            self._last_mute_end = max(self._last_mute_end, end)

            self._schedule.add(start, end)

            # Если этот кусок уже ушёл в эфир, заглушать нечего — честно
            # показываем это в ленте, чтобы было видно, что буфер мал.
            played = self._ring.read_pos if self._ring is not None else 0
            if end <= played:
                self.missed += 1
                self.profanity.emit(word.text, "не успели: увеличьте задержку")
            else:
                self.profanity.emit(word.text, match.rule)

        # Модель дала промежуточный текст без таймингов, а мат уже слышен —
        # глушим от текущего момента, не дожидаясь точного времени слова.
        if not result.is_final and result.text and not result.words:
            words = result.text.split()
            if words and self.matcher.check(words[-1]) is not None:
                now = self._ring.write_pos if self._ring is not None else 0
                self._schedule.add(max(0, now - pre - int(sr * 0.25)), now + post)
                self.profanity.emit(words[-1], "partial")

    # ----------------------------------------------------- применение настроек
    def reload_sound(self) -> None:
        if self._sound is not None:
            self._sound.load(self.cfg.mute)

    def panic(self, enabled: bool) -> None:
        self.manual_mute = enabled
        self.mute_state.emit(enabled)
