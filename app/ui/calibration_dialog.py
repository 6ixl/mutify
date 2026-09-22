# -*- coding: utf-8 -*-
"""Мастер калибровки микрофона: запись пробной фразы и разбор результата."""
from __future__ import annotations

import queue

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget
)

from app.audio.calibration import Calibration, analyse
from app.branding import APP_NAME
from app.ui import theme
from app.ui.widgets import Badge, Card, LevelMeter

PHRASE = "Раз, два, три. Проверка микрофона, меня хорошо слышно?"
RECORD_SECONDS = 6


class CalibrationDialog(QDialog):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} — калибровка микрофона")
        self.setMinimumWidth(560)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        self._stream = None
        self._queue: queue.Queue = queue.Queue()
        self._chunks: list[np.ndarray] = []
        self._result: Calibration | None = None
        self._elapsed = 0.0

        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Калибровка микрофона")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.step_label = QLabel(
            "Нажмите «Начать» и прочитайте фразу обычным голосом — так же, "
            "как будете говорить в игре или на стриме."
        )
        self.step_label.setObjectName("PageHint")
        self.step_label.setWordWrap(True)
        root.addWidget(self.step_label)

        phrase_card = Card("Прочитайте вслух")
        self.phrase_label = QLabel(f"«{PHRASE}»")
        self.phrase_label.setObjectName("Transcript")
        self.phrase_label.setWordWrap(True)
        phrase_card.add(self.phrase_label)
        root.addWidget(phrase_card)

        meter_card = Card("Уровень")
        self.meter = LevelMeter()
        meter_card.add(self.meter)
        self.progress = QProgressBar()
        self.progress.setRange(0, RECORD_SECONDS * 10)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {theme.BG}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {theme.ACCENT}; border-radius: 3px; }}"
        )
        meter_card.add(self.progress)
        root.addWidget(meter_card)

        self.result_card = Card("Результат")
        self.verdict_badge = Badge("ещё не проверяли", theme.TEXT_MUTED)
        badge_line = QHBoxLayout()
        badge_line.addWidget(self.verdict_badge)
        badge_line.addStretch(1)
        self.result_card.add_layout(badge_line)

        self.numbers_label = QLabel("—")
        self.numbers_label.setObjectName("Hint")
        self.numbers_label.setWordWrap(True)
        self.result_card.add(self.numbers_label)

        self.heard_label = QLabel()
        self.heard_label.setWordWrap(True)
        self.result_card.add(self.heard_label)

        self.tips_label = QLabel()
        self.tips_label.setObjectName("Hint")
        self.tips_label.setWordWrap(True)
        self.result_card.add(self.tips_label)
        root.addWidget(self.result_card)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.start_btn = QPushButton("Начать")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._start)
        buttons.addWidget(self.start_btn)

        self.apply_btn = QPushButton("Применить усиление")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_gain)
        buttons.addWidget(self.apply_btn)

        buttons.addStretch(1)
        close = QPushButton("Закрыть")
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------- запись
    def _start(self) -> None:
        import sounddevice as sd

        if self.ctx.engine.running:
            self.ctx.notify("Остановите мут перед калибровкой", False)
            return

        self._chunks.clear()
        self._queue = queue.Queue()
        self._elapsed = 0.0
        self._result = None
        self.apply_btn.setEnabled(False)
        self.progress.setValue(0)
        self.verdict_badge.set_state("идёт запись...", theme.ACCENT)
        self.numbers_label.setText("Говорите...")
        self.heard_label.clear()
        self.tips_label.clear()

        sr = self.ctx.cfg.audio.samplerate
        try:
            self._stream = sd.InputStream(
                device=self.ctx.cfg.audio.input_device,
                channels=1,
                samplerate=sr,
                blocksize=512,
                dtype="float32",
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as exc:
            self.verdict_badge.set_state("микрофон недоступен", theme.DANGER)
            self.numbers_label.setText(str(exc))
            return

        self.start_btn.setEnabled(False)
        self.step_label.setText("Читайте фразу вслух, осталось несколько секунд.")
        self._timer.start(100)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._queue.put(indata[:, 0].copy())

    def _tick(self) -> None:
        sr = self.ctx.cfg.audio.samplerate
        latest = None
        while True:
            try:
                block = self._queue.get_nowait()
            except queue.Empty:
                break
            self._chunks.append(block)
            latest = block

        if latest is not None:
            self.meter.set_level(float(np.sqrt(np.mean(latest ** 2)) * 3.0))

        self._elapsed += 0.1
        self.progress.setValue(int(self._elapsed * 10))
        if self._elapsed >= RECORD_SECONDS:
            self._finish(sr)

    # ------------------------------------------------------------- разбор
    def _finish(self, samplerate: int) -> None:
        self._timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        self.start_btn.setEnabled(True)
        self.start_btn.setText("Проверить ещё раз")
        self.step_label.setText("Готово. Вот что услышал микрофон и модель.")

        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        result = analyse(audio, samplerate)
        result.recognized, result.words = self._transcribe(audio, samplerate)
        # советы зависят и от распознавания, поэтому пересобираем вердикт
        result.tips.clear()
        from app.audio.calibration import _verdict

        _verdict(result)
        self._result = result
        self._show(result)

    def _transcribe(self, audio: np.ndarray, samplerate: int) -> tuple[str, int]:
        """Прогоняет запись через ту же модель, что работает в муте."""
        if len(audio) == 0:
            return "", 0
        try:
            from app.stt import factory

            engine = factory.create(self.ctx.cfg.ai, samplerate)
            engine.start()
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
            texts = []
            step = samplerate * 2          # кормим по секунде звука
            for start in range(0, len(pcm), step):
                for res in engine.feed(pcm[start:start + step]):
                    if res.is_final and res.text:
                        texts.append(res.text)
            for res in engine.flush():
                if res.text:
                    texts.append(res.text)
            engine.stop()
            text = " ".join(texts).strip()
            return text, len(text.split())
        except Exception:
            return "", 0

    def _show(self, result: Calibration) -> None:
        colors = {
            "ok": theme.OK, "quiet": theme.WARN, "loud": theme.WARN,
            "clipping": theme.DANGER, "silent": theme.DANGER,
        }
        self.verdict_badge.set_state(
            result.verdict, colors.get(result.level, theme.TEXT_MUTED)
        )
        self.numbers_label.setText(
            "Громкость речи: {:.1f} дБ   ·   пик: {:.1f} дБ   ·   фон: {:.1f} дБ\n"
            "Запас над шумом: {:.1f} дБ   ·   речь занимала {:.0f}% времени".format(
                result.rms_db, result.peak_db, result.noise_db,
                result.signal_to_noise, result.speech_ratio * 100,
            )
        )

        if result.recognized:
            self.heard_label.setText(
                f'<span style="color:{theme.TEXT_MUTED}">Модель услышала:</span> '
                f'<span style="color:{theme.TEXT}">{result.recognized}</span>'
            )
        else:
            self.heard_label.setText(
                f'<span style="color:{theme.DANGER}">Модель не разобрала ни слова</span>'
            )

        tips = list(result.tips)
        if abs(result.suggested_gain_db) >= 1.0:
            tips.insert(0, f"Рекомендуемое усиление: {result.suggested_gain_db:+.1f} дБ.")
            self.apply_btn.setEnabled(True)
            self.apply_btn.setText(f"Применить {result.suggested_gain_db:+.1f} дБ")
        else:
            tips.insert(0, "Усиление менять не нужно.")
            self.apply_btn.setEnabled(False)
            self.apply_btn.setText("Применить усиление")
        self.tips_label.setText("\n".join("• " + t for t in tips))

    # ------------------------------------------------------------ действия
    def _apply_gain(self) -> None:
        if self._result is None:
            return
        current = self.ctx.cfg.audio.input_gain_db
        value = max(-20.0, min(20.0, current + self._result.suggested_gain_db))
        self.ctx.cfg.audio.input_gain_db = round(value, 1)
        self.ctx.save_and_apply()
        self.ctx.notify(f"Усиление микрофона: {value:+.1f} дБ", True)
        self.apply_btn.setEnabled(False)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        super().closeEvent(event)
