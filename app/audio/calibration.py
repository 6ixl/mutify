# -*- coding: utf-8 -*-
"""Разбор пробной записи: достаточно ли громко говорит микрофон и слышит ли модель."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Куда целимся: речь в среднем около -20 dBFS, пики не выше -3 dBFS.
TARGET_RMS_DB = -20.0
PEAK_CEILING_DB = -3.0
SPEECH_GATE_DB = -45.0      # тише этого считаем паузой, а не речью


def to_db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-9))


@dataclass
class Calibration:
    rms_db: float = -99.0
    peak_db: float = -99.0
    noise_db: float = -99.0
    speech_ratio: float = 0.0        # доля времени, когда вы говорили
    clipping: float = 0.0            # доля сэмплов на пределе
    suggested_gain_db: float = 0.0
    recognized: str = ""
    words: int = 0
    verdict: str = ""
    level: str = "unknown"           # ok | quiet | loud | clipping | silent
    tips: list[str] = field(default_factory=list)

    @property
    def signal_to_noise(self) -> float:
        return self.rms_db - self.noise_db


def analyse(audio: np.ndarray, samplerate: int) -> Calibration:
    """Считает уровни по записи и подбирает усиление."""
    result = Calibration()
    if len(audio) == 0:
        result.verdict = "Запись пустая — микрофон ничего не передал."
        result.level = "silent"
        return result

    # Разбиваем на окна по 30 мс: так отделяем речь от пауз.
    frame = max(1, int(samplerate * 0.03))
    frames = len(audio) // frame
    if frames == 0:
        frames, frame = 1, len(audio)
    blocks = audio[: frames * frame].reshape(frames, frame)
    rms_per_block = np.sqrt(np.mean(blocks.astype(np.float64) ** 2, axis=1))
    db_per_block = np.array([to_db(v) for v in rms_per_block])

    speech = db_per_block > SPEECH_GATE_DB
    result.speech_ratio = float(speech.mean())
    result.peak_db = to_db(float(np.max(np.abs(audio))))
    result.clipping = float(np.mean(np.abs(audio) > 0.985))

    if speech.any():
        result.rms_db = float(np.mean(db_per_block[speech]))
    else:
        result.rms_db = float(np.mean(db_per_block))
    quiet_blocks = db_per_block[~speech]
    result.noise_db = float(np.mean(quiet_blocks)) if quiet_blocks.size else -90.0

    # Подбор усиления: подтягиваем речь к цели, но не даём пикам уйти в клиппинг.
    gain = TARGET_RMS_DB - result.rms_db
    headroom = PEAK_CEILING_DB - result.peak_db
    gain = min(gain, headroom)
    result.suggested_gain_db = round(max(-20.0, min(20.0, gain)), 1)

    _verdict(result)
    return result


def _verdict(result: Calibration) -> None:
    if result.speech_ratio < 0.04 or result.rms_db < -55:
        result.level = "silent"
        result.verdict = "Микрофон почти ничего не слышит."
        result.tips.append(
            "Проверьте, что выбран правильный микрофон и он не выключен в Windows."
        )
        return

    if result.clipping > 0.005 or result.peak_db > -0.5:
        result.level = "clipping"
        result.verdict = "Сигнал перегружен — звук режется на пиках."
        result.tips.append("Убавьте громкость микрофона в Windows или отодвиньтесь от него.")
    elif result.rms_db < TARGET_RMS_DB - 8:
        result.level = "quiet"
        result.verdict = "Микрофон тихий — модель будет чаще ошибаться."
        result.tips.append("Примените предложенное усиление или говорите ближе к микрофону.")
    elif result.rms_db > TARGET_RMS_DB + 8:
        result.level = "loud"
        result.verdict = "Громковато, но терпимо."
    else:
        result.level = "ok"
        result.verdict = "Уровень в самый раз."

    if result.signal_to_noise < 15:
        result.tips.append(
            "Много фонового шума: между словами слышен гул. "
            "Модель может принимать шум за слова."
        )
    if result.words == 0:
        result.tips.append(
            "Модель не разобрала ни одного слова. Проверьте, что скачана русская модель."
        )
    elif result.words < 3:
        result.tips.append("Разобрано мало слов — попробуйте говорить чуть отчётливее.")
