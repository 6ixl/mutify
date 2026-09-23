# -*- coding: utf-8 -*-
"""Приведение любого звукового файла к простому wav.

Люди приносят что угодно: mp3 с гигантским тегом, m4a, вырезку из видео, файл
с расширением .mp3, внутри которого на самом деле MP4. libsndfile понимает
далеко не всё, поэтому пробуем по очереди несколько декодеров и кладём рядом
готовый wav — движок дальше работает только с ним.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

DECODED_SUFFIX = ".decoded.wav"


def decoded_path(source: Path) -> Path:
    return source.with_name(source.stem + DECODED_SUFFIX)


def load_audio(path: str | Path, samplerate: int) -> tuple[np.ndarray, str]:
    """Возвращает моно-дорожку в нужной частоте и название сработавшего способа.

    Бросает RuntimeError с понятным текстом, если файл не осилил никто.
    """
    source = Path(path)
    if not source.exists():
        raise RuntimeError("Файл не найден: " + str(source))

    # Уже конвертированная копия рядом — самый быстрый путь.
    cached = decoded_path(source)
    if cached.exists() and cached.stat().st_mtime >= source.stat().st_mtime:
        data = _read_with_soundfile(cached, samplerate)
        if data is not None:
            return data, "готовый wav"

    data = _read_with_soundfile(source, samplerate)
    if data is not None:
        return data, "libsndfile"

    errors = []
    for name, reader in (("ffmpeg", _read_with_ffmpeg), ("Windows", _read_with_qt)):
        try:
            data = reader(source, samplerate)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if data is not None and len(data):
            _save_wav(cached, data, samplerate)
            return data, name
        errors.append(f"{name}: пустой результат")

    raise RuntimeError(
        "Не удалось прочитать звук. Формат не поддерживается: "
        + "; ".join(errors[:2])
    )


# ------------------------------------------------------------------ способы
def _read_with_soundfile(path: Path, samplerate: int) -> np.ndarray | None:
    try:
        import soundfile as sf

        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        return None
    if len(data) == 0:
        return None
    return _prepare(data.mean(axis=1), sr, samplerate)


def _read_with_ffmpeg(path: Path, samplerate: int) -> np.ndarray | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    command = [
        exe, "-v", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(samplerate),
        "-f", "f32le", "-",
    ]
    result = subprocess.run(
        command, capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 or not result.stdout:
        message = (result.stderr or b"").decode("utf-8", "ignore").strip()
        raise RuntimeError(message.splitlines()[-1] if message else "не смог декодировать")
    return np.frombuffer(result.stdout, dtype=np.float32).copy()


def _read_with_qt(path: Path, samplerate: int) -> np.ndarray | None:
    """Системные кодеки Windows через Qt — берут mp3, m4a, aac и звук из видео."""
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("нет приложения Qt")

    fmt = QAudioFormat()
    fmt.setSampleRate(samplerate)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.Float)

    decoder = QAudioDecoder()
    decoder.setAudioFormat(fmt)
    decoder.setSource(QUrl.fromLocalFile(str(path)))

    pieces: list[np.ndarray] = []
    loop = QEventLoop()
    failure: list[str] = []

    def on_buffer() -> None:
        buffer = decoder.read()
        if buffer.isValid():
            pieces.append(np.array(buffer.data(), dtype=np.float32, copy=True))

    def on_error(*_) -> None:
        failure.append(decoder.errorString() or "ошибка декодирования")
        loop.quit()

    decoder.bufferReady.connect(on_buffer)
    decoder.finished.connect(loop.quit)
    decoder.error.connect(on_error)
    decoder.start()
    QTimer.singleShot(30000, loop.quit)      # страховка от зависания
    loop.exec()
    decoder.stop()

    if failure:
        raise RuntimeError(failure[0])
    if not pieces:
        return None
    return np.concatenate(pieces)


# ------------------------------------------------------------- вспомогательное
def _prepare(mono: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    mono = np.asarray(mono, dtype=np.float32)
    if source_rate != target_rate and len(mono) > 1:
        count = int(len(mono) * target_rate / source_rate)
        mono = np.interp(
            np.linspace(0, len(mono) - 1, count),
            np.arange(len(mono)),
            mono,
        ).astype(np.float32)
    return mono


def _save_wav(path: Path, data: np.ndarray, samplerate: int) -> None:
    try:
        import soundfile as sf

        sf.write(str(path), data, samplerate, subtype="PCM_16")
    except Exception:
        pass        # кэш не обязателен, просто ускоряет следующий запуск
