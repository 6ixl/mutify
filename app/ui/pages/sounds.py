# -*- coding: utf-8 -*-
"""Страница заглушения: чем подменять мат и насколько широко его вырезать."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QVBoxLayout, QWidget
)

from app.paths import SOUNDS_DIR
from app.ui import theme
from app.ui.widgets import Card, SliderRow

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


class SoundsPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Заглушение")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel("Чем подменять мат и насколько широко вырезать слово.")
        hint.setObjectName("PageHint")
        root.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._mode_card(), 1)
        columns.addWidget(self._shape_card(), 1)
        root.addLayout(columns)

        root.addWidget(self._library_card(), 1)

    # ------------------------------------------------------------ режим
    def _mode_card(self) -> Card:
        cfg = self.ctx.cfg.mute
        card = Card("Чем заменять")
        box = card.body()

        self.mode_group = QButtonGroup(self)
        modes = (
            ("sound", "Свой звук", "Файл из библиотеки ниже. Зацикливается на время мата."),
            ("beep", "Встроенный сигнал", "Классический цензурный «бип» 950 Гц."),
            ("silence", "Тишина", "Просто вырезать звук без подмены."),
        )
        for value, label, note in modes:
            button = QRadioButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(cfg.mode == value)
            button.toggled.connect(
                lambda checked, v=value: self._set_mode(v) if checked else None
            )
            self.mode_group.addButton(button)
            box.addWidget(button)
            sub = QLabel(note)
            sub.setObjectName("Hint")
            sub.setWordWrap(True)
            sub.setContentsMargins(24, 0, 0, 6)
            box.addWidget(sub)

        self.volume = SliderRow(
            "Громкость заглушки", 0, 200, int(cfg.sound_volume * 100), " %",
            "Насколько громко звучит подмена. Значение можно вписать вручную — "
            "вплоть до 1000%, если звук слишком тихий. Выше 100% возможна "
            "перегрузка, следите за хрипом.",
            hard_min=0, hard_max=1000,
        )
        self.volume.changed.connect(self._set_volume)
        box.addWidget(self.volume)
        box.addStretch(1)
        return card

    def _shape_card(self) -> Card:
        cfg = self.ctx.cfg.mute
        card = Card("Точность выреза")
        box = card.body()

        self.pre = SliderRow(
            "Запас до слова", 0, 500, cfg.pre_pad_ms, " мс",
            "Глушить чуть раньше начала слова — страхует от неточного тайминга модели.",
            step=10,
        )
        self.pre.changed.connect(lambda v: self._set("pre_pad_ms", v))
        box.addWidget(self.pre)

        self.post = SliderRow(
            "Запас после слова", 0, 800, cfg.post_pad_ms, " мс",
            "Захватывает хвост слова и окончание, которое модель могла не дослышать.",
            step=10,
        )
        self.post.changed.connect(lambda v: self._set("post_pad_ms", v))
        box.addWidget(self.post)

        self.fade = SliderRow(
            "Сглаживание краёв", 1, 80, cfg.fade_ms, " мс",
            "Убирает щелчки на входе и выходе из заглушения.",
        )
        self.fade.changed.connect(lambda v: self._set("fade_ms", v))
        box.addWidget(self.fade)

        self.burst = SliderRow(
            "Склеивать серию матов", 0, 2000, cfg.burst_ms, " мс",
            "Когда вы материтесь быстро, модель успевает разобрать не каждое "
            "слово. Промежуток между двумя близкими матами тоже заглушается, "
            "чтобы пропущенное не просочилось. 0 — выключить.",
            step=50,
        )
        self.burst.changed.connect(lambda v: self._set("burst_ms", v))
        box.addWidget(self.burst)
        box.addStretch(1)
        return card

    # ------------------------------------------------------------ библиотека
    def _library_card(self) -> Card:
        card = Card(
            "Библиотека звуков",
            f"Файлы лежат в папке {SOUNDS_DIR}. Добавленные сюда звуки доступны сразу.",
        )
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_select)
        card.add(self.list)

        line = QHBoxLayout()
        line.setSpacing(8)
        add = QPushButton("Добавить файл...")
        add.clicked.connect(self._add_file)
        line.addWidget(add)

        play = QPushButton("Прослушать")
        play.setObjectName("Ghost")
        play.clicked.connect(self._preview)
        line.addWidget(play)

        remove = QPushButton("Удалить")
        remove.setObjectName("Ghost")
        remove.clicked.connect(self._remove_file)
        line.addWidget(remove)

        line.addStretch(1)
        self.current_label = QLabel()
        self.current_label.setObjectName("Hint")
        line.addWidget(self.current_label)
        card.add_layout(line)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        card.add(self.status_label)

        self.reload()
        return card

    def reload(self) -> None:
        cfg = self.ctx.cfg.mute
        self.list.blockSignals(True)
        self.list.clear()
        for path in sorted(SOUNDS_DIR.iterdir()) if SOUNDS_DIR.exists() else []:
            if path.suffix.lower() not in AUDIO_EXT:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            self.list.addItem(item)
            if str(path) == cfg.sound_path:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self._update_current()

    def _update_current(self) -> None:
        path = self.ctx.cfg.mute.sound_path
        name = Path(path).name if path else "не выбран"
        self.current_label.setText(f"выбран: {name}")
        self._check_sound(path)

    def _check_sound(self, path: str) -> None:
        """Проверяем, что файл действительно читается, и говорим об этом вслух."""
        if not hasattr(self, "status_label"):
            return
        if self.ctx.cfg.mute.mode != "sound" or not path:
            self.status_label.setText("")
            return

        from app.audio.muter import ReplacementSound

        probe = ReplacementSound(self.ctx.cfg.audio.samplerate)
        probe.load(self.ctx.cfg.mute)
        if probe.error:
            self.status_label.setText(
                "\n".join((
                    "Этот файл не читается: " + probe.error,
                    "Поставьте другой файл или сконвертируйте его в wav.",
                ))
            )
            self.status_label.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px;")
        else:
            seconds = len(probe._data) / max(1, self.ctx.cfg.audio.samplerate)
            how = f" (через {probe.how})" if probe.how not in ("libsndfile", "") else ""
            self.status_label.setText(
                f"Звук готов: {seconds:.1f} с{how}"
            )
            self.status_label.setStyleSheet(f"color: {theme.OK}; font-size: 11px;")

    # ------------------------------------------------------------ действия
    def reload_values(self) -> None:
        """Подтянуть значения из настроек — например, после смены профиля."""
        cfg = self.ctx.cfg.mute
        self.volume.set_value(int(cfg.sound_volume * 100), silent=True)
        self.pre.set_value(cfg.pre_pad_ms, silent=True)
        self.post.set_value(cfg.post_pad_ms, silent=True)
        self.fade.set_value(cfg.fade_ms, silent=True)
        self.burst.set_value(cfg.burst_ms, silent=True)
        labels = {"sound": "Свой звук", "beep": "Встроенный сигнал", "silence": "Тишина"}
        target = labels.get(cfg.mode)
        for button in self.mode_group.buttons():
            button.blockSignals(True)
            button.setChecked(button.text() == target)
            button.blockSignals(False)
        self.reload()

    def _set_mode(self, mode: str) -> None:
        self.ctx.cfg.mute.mode = mode
        self.ctx.save_and_apply()

    def _set_volume(self, value: int) -> None:
        self.ctx.cfg.mute.sound_volume = value / 100.0
        self.ctx.save_and_apply()

    def _set(self, field: str, value: int) -> None:
        setattr(self.ctx.cfg.mute, field, value)
        self.ctx.save_and_apply()

    def _on_select(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.ctx.cfg.mute.sound_path = item.data(Qt.UserRole)
        if self.ctx.cfg.mute.mode != "sound":
            self.ctx.cfg.mute.mode = "sound"
            for button in self.mode_group.buttons():
                button.setChecked(button.text() == "Свой звук")
        self.ctx.save_and_apply()
        self._update_current()

    def _add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите звук", "", "Аудио (*.wav *.mp3 *.ogg *.flac *.m4a)"
        )
        if not path:
            return
        source = Path(path)
        target = SOUNDS_DIR / source.name
        if source.parent != SOUNDS_DIR:
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                self.ctx.notify(f"Не удалось скопировать: {exc}", False)
                return
        self.ctx.cfg.mute.sound_path = str(target)
        self.ctx.cfg.mute.mode = "sound"
        self.ctx.save_and_apply()
        self.reload()

        from app.audio.muter import ReplacementSound

        probe = ReplacementSound(self.ctx.cfg.audio.samplerate)
        probe.load(self.ctx.cfg.mute)
        if probe.error:
            self.ctx.notify("Файл не читается: " + probe.error, False)
        else:
            self.ctx.notify(f"Звук добавлен: {target.name}", True)

    def _remove_file(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        try:
            path.unlink()
        except OSError as exc:
            self.ctx.notify(f"Не удалось удалить: {exc}", False)
            return
        if self.ctx.cfg.mute.sound_path == str(path):
            self.ctx.cfg.mute.sound_path = ""
            self.ctx.save_and_apply()
        self.reload()

    def _preview(self) -> None:
        """Проигрывает выбранный звук на устройстве по умолчанию."""
        import numpy as np
        import sounddevice as sd

        from app.audio.muter import ReplacementSound

        sound = ReplacementSound(44100)
        sound.load(self.ctx.cfg.mute)
        data = sound.take(int(44100 * 1.0), self.ctx.cfg.mute.sound_volume)
        try:
            sd.play(np.asarray(data, dtype="float32"), 44100)
        except Exception as exc:
            self.ctx.notify(f"Не удалось воспроизвести: {exc}", False)
