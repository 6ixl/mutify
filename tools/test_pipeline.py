# -*- coding: utf-8 -*-
"""Честная проверка конвейера: прогоняет запись через настоящие аудио-callback'и
движка в реальном темпе и смотрит, что оказалось НА ВЫХОДЕ.

Запуск:  python tools/test_pipeline.py путь_к_wav
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.audio.engine import AudioEngine  # noqa: E402
from app.audio.muter import MuteSchedule, ReplacementSound  # noqa: E402
from app.audio.ringbuffer import DelayRing  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.filter.matcher import ProfanityMatcher  # noqa: E402
from app.filter.wordlist import WordList  # noqa: E402
from app.stt import factory  # noqa: E402
from app.stt.vosk_engine import VoskSTT  # noqa: E402

BLOCK = 512


def run(wav_path: str, realtime: bool = True) -> None:
    QApplication.instance() or QApplication([])

    audio, sr = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    cfg = AppConfig()
    cfg.audio.samplerate = sr
    cfg.ai.model_path = VoskSTT.autodetect_model()
    cfg.mute.mode = "beep"
    # ENGINE=whisper — проверить конвейер на Whisper вместо Vosk
    cfg.ai.engine = os.environ.get("ENGINE", "vosk")
    if cfg.ai.engine == "whisper":
        cfg.mute.delay_ms = max(cfg.mute.delay_ms, 700)

    matcher = ProfanityMatcher(WordList.load(), cfg.ai)
    engine = AudioEngine(cfg, matcher)
    engine._ring = DelayRing(sr, capacity_ms=max(4000, cfg.mute.delay_ms * 4))
    engine._schedule = MuteSchedule()
    engine._sound = ReplacementSound(sr)
    engine._sound.load(cfg.mute)
    engine._out_channels = 1
    engine._stt = factory.create(cfg.ai, sr)
    engine._stt.start()
    engine.running = True

    # Сигналы Qt из чужого потока без цикла событий не доходят, поэтому
    # ловим сами добавленные интервалы.
    hits = []
    added = []
    original_add = engine._schedule.add

    def tracking_add(start, end, restart=True):
        added.append((start, end))
        hits.append(("слово", "интервал"))
        original_add(start, end, restart)

    engine._schedule.add = tracking_add

    import threading

    thread = threading.Thread(target=engine._stt_loop, daemon=True)
    thread.start()

    out_blocks = []
    out_positions = []
    original_read = engine._ring.read

    def tracking_read(n, delay):
        data, pos = original_read(n, delay)
        out_positions.append(pos)
        return data, pos

    engine._ring.read = tracking_read

    block_seconds = BLOCK / sr
    started = time.monotonic()
    for index in range(0, len(audio) - BLOCK, BLOCK):
        chunk = audio[index:index + BLOCK].reshape(-1, 1)
        engine._on_input(chunk, BLOCK, None, None)

        out = np.zeros((BLOCK, 1), dtype=np.float32)
        engine._on_output(out, BLOCK, None, None)
        out_blocks.append(out[:, 0].copy())

        if realtime:
            target = started + (index / BLOCK + 1) * block_seconds
            sleep_for = target - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

    # даём модели договорить и сливаем хвост задержки
    time.sleep(0.6)
    for _ in range(int(sr * 1.2 / BLOCK)):
        engine._on_input(np.zeros((BLOCK, 1), dtype=np.float32), BLOCK, None, None)
        out = np.zeros((BLOCK, 1), dtype=np.float32)
        engine._on_output(out, BLOCK, None, None)
        out_blocks.append(out[:, 0].copy())

    engine.running = False
    engine._stt_queue.put(None)
    thread.join(timeout=2)

    output = np.concatenate(out_blocks)
    positions = np.array(out_positions)

    print("файл            :", Path(wav_path).name)
    # Склеиваем пересекающиеся интервалы, чтобы проверять цельные участки.
    merged = []
    for start, end in sorted(added):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    print("заглушений      :", len(merged))
    print("интервалы мута  :", [(round(a / sr, 2), round(b / sr, 2)) for a, b in merged])

    # Сравниваем выход с оригиналом на участках, которые должны быть заглушены.
    ok = True
    for start, end in merged:
        block_indexes = [i for i, p in enumerate(positions)
                         if start <= p < end and i < len(out_blocks)]
        if not block_indexes:
            print("  ВЫХОД НЕ ЗАТРОНУТ: интервал %.2f-%.2f с не попал в поток вывода"
                  % (start / sr, end / sr))
            ok = False
            continue
        got = np.concatenate([out_blocks[i] for i in block_indexes])
        source_start = positions[block_indexes[0]]
        original = audio[source_start:source_start + len(got)]
        if len(original) < len(got):
            original = np.pad(original, (0, len(got) - len(original)))
        difference = float(np.mean(np.abs(got - original)))
        loud = float(np.sqrt(np.mean(got ** 2)))
        print("  участок %.2f-%.2f с: отличие от оригинала %.3f, громкость выхода %.3f"
              % (start / sr, end / sr, difference, loud))
        if difference < 0.02:
            print("    МАТ ПРОШЁЛ В ЭФИР — звук не подменён")
            ok = False

    print("ИТОГ:", "мат вырезан" if ok else "ПРОБЛЕМА: мат прошёл в эфир")
    return ok


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "phrase.wav"
    run(path)
