# -*- coding: utf-8 -*-
"""Страница аудио: маршрут звука, задержка упреждения, громкости."""
from __future__ import annotations

import webbrowser

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from app.audio import devices
from app.audio.cable_installer import CableInstaller
from app.audio.devices import VB_HINTS
from app.ui import theme
from app.ui.widgets import (
    Badge, Card, DeviceCombo, FlowLayout, Row, SliderRow, ToggleSwitch, hint_label
)

VB_DOWNLOAD = "https://vb-audio.com/Cable/"


class AudioPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._installer = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        holder = QWidget()
        scroll.setWidget(holder)
        root = QVBoxLayout(holder)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Аудио")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Приложение встаёт между микрофоном и Дискордом: забирает звук с микрофона "
            "и отдаёт очищенный в виртуальный кабель."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._route_card())
        root.addWidget(self._delay_card())
        root.addWidget(self._levels_card())
        root.addWidget(self._processing_card())
        root.addWidget(self._cable_card())
        root.addStretch(1)

    # ------------------------------------------------------------ маршрут
    def _route_card(self) -> Card:
        cfg = self.ctx.cfg.audio
        card = Card("Маршрут звука")
        box = card.body()

        self.input_combo = DeviceCombo()
        self.input_combo.currentIndexChanged.connect(
            lambda: self._set("input_device", self.input_combo.selected_device())
        )
        box.addWidget(Row("Микрофон", self.input_combo, "Откуда берём ваш голос."))

        self.output_combo = DeviceCombo()
        self.output_combo.currentIndexChanged.connect(
            lambda: self._set("output_device", self.output_combo.selected_device())
        )
        box.addWidget(
            Row(
                "Выход (виртуальный кабель)",
                self.output_combo,
                "Это устройство нужно выбрать микрофоном в Дискорде или OBS. "
                "Звёздочкой помечены найденные виртуальные кабели.",
            )
        )

        self.monitor_toggle = ToggleSwitch()
        self.monitor_toggle.setChecked(cfg.monitor_enabled)
        self.monitor_toggle.toggled.connect(
            lambda v: self._set("monitor_enabled", v)
        )
        box.addWidget(
            Row("Прослушка в наушники", self.monitor_toggle,
                "Дублирует очищенный звук вам, чтобы слышать, как вас слышат другие.")
        )

        self.monitor_combo = DeviceCombo()
        self.monitor_combo.currentIndexChanged.connect(
            lambda: self._set("monitor_device", self.monitor_combo.selected_device())
        )
        box.addWidget(Row("Устройство прослушки", self.monitor_combo))

        line = FlowLayout(spacing=8)
        refresh = QPushButton("Обновить список устройств")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.reload_devices)
        line.addWidget(refresh)

        auto = QPushButton("Подобрать автоматически")
        auto.setObjectName("Ghost")
        auto.clicked.connect(self._autoselect)
        line.addWidget(auto)
        box.addLayout(line)

        self.reload_devices()
        return card

    # ------------------------------------------------------------ задержка
    def _delay_card(self) -> Card:
        cfg = self.ctx.cfg.mute
        card = Card(
            "Буфер упреждения",
            "Главная настройка. Модель узнаёт слово только после того, как оно прозвучало, "
            "поэтому звук едет к собеседнику с задержкой — за это время мат успевают вырезать.",
        )
        box = card.body()

        self.delay = SliderRow(
            "Задержка звука", 100, 2000, cfg.delay_ms, " мс",
            "400 мс — живой разговор и надёжный перехват. "
            "Меньше 250 мс мат начнёт проскакивать. Для Whisper ставьте от 1000 мс.",
            step=25,
        )
        self.delay.changed.connect(self._set_delay)
        box.addWidget(self.delay)

        self.delay_note = QLabel()
        self.delay_note.setObjectName("Hint")
        self.delay_note.setWordWrap(True)
        box.addWidget(self.delay_note)
        self._update_delay_note(cfg.delay_ms)

        self.block = SliderRow(
            "Размер аудиоблока", 128, 2048, self.ctx.cfg.audio.blocksize, " сэмплов",
            "Меньше — ниже задержка драйвера, но выше риск щелчков. "
            "512 подходит почти всем.",
            step=128,
        )
        self.block.changed.connect(
            lambda v: self._set("blocksize", max(128, v // 128 * 128))
        )
        box.addWidget(self.block)
        return card

    def _levels_card(self) -> Card:
        cfg = self.ctx.cfg.audio
        card = Card("Громкость")
        box = card.body()

        self.in_gain = SliderRow(
            "Усиление микрофона", -20, 20, int(cfg.input_gain_db), " дБ",
            "Поднимите, если модель плохо слышит тихий микрофон. "
            "Значение можно вписать вручную, ползунок показывает обычный диапазон. "
            "Выше +20 дБ следите за перегрузкой — звук начнёт хрипеть.",
            hard_min=-90, hard_max=90,
        )
        self.in_gain.changed.connect(lambda v: self._set("input_gain_db", float(v)))
        box.addWidget(self.in_gain)

        self.out_gain = SliderRow(
            "Громкость на выходе", -20, 20, int(cfg.output_gain_db), " дБ",
            "Тоже вводится вручную, если нужно больше шкалы.",
            hard_min=-90, hard_max=90,
        )
        self.out_gain.changed.connect(lambda v: self._set("output_gain_db", float(v)))
        box.addWidget(self.out_gain)

        line = QHBoxLayout()
        calibrate = QPushButton("Калибровка микрофона...")
        calibrate.setToolTip(
            "Запишет пробную фразу, измерит уровень и подберёт усиление"
        )
        calibrate.clicked.connect(self._open_calibration)
        line.addWidget(calibrate)
        line.addStretch(1)
        box.addLayout(line)
        return card

    def _processing_card(self) -> Card:
        cfg = self.ctx.cfg.audio
        card = Card(
            "Обработка звука",
            "По умолчанию приложение ничего не «улучшает»: микрофон передаётся "
            "как есть, без шумоподавления и автогромкости.",
        )
        box = card.body()

        self.gate_toggle = ToggleSwitch()
        self.gate_toggle.setChecked(cfg.noise_gate)
        self.gate_toggle.toggled.connect(self._toggle_gate)
        box.addWidget(
            Row("Шумоподавление", self.gate_toggle,
                "Приглушает паузы между словами: убирает гул вентиляторов и шум "
                "комнаты. Включайте, только если фон действительно мешает.")
        )

        self.gate_threshold = SliderRow(
            "Порог шума", -70, -20, int(cfg.gate_threshold_db), " дБ",
            "Всё тише этого уровня считается шумом. Слишком высокий порог "
            "начнёт срезать окончания слов.",
        )
        self.gate_threshold.changed.connect(
            lambda v: self._set("gate_threshold_db", float(v))
        )
        box.addWidget(self.gate_threshold)

        self.gate_release = SliderRow(
            "Плавность", 20, 500, cfg.gate_release_ms, " мс",
            "Насколько мягко шумоподавление открывается и закрывается.",
            step=10,
        )
        self.gate_release.changed.connect(lambda v: self._set("gate_release_ms", v))
        box.addWidget(self.gate_release)

        self._update_gate_enabled(cfg.noise_gate)
        return card

    def _toggle_gate(self, enabled: bool) -> None:
        self._set("noise_gate", enabled)
        self._update_gate_enabled(enabled)

    def _update_gate_enabled(self, enabled: bool) -> None:
        self.gate_threshold.setEnabled(enabled)
        self.gate_release.setEnabled(enabled)

    def _cable_card(self) -> Card:
        card = Card("Виртуальный микрофон")
        box = card.body()

        self.cable_badge = Badge()
        row = QHBoxLayout()
        row.addWidget(self.cable_badge)
        row.addStretch(1)
        box.addLayout(row)

        self.cable_hint = QLabel()
        self.cable_hint.setObjectName("Hint")
        self.cable_hint.setWordWrap(True)
        box.addWidget(self.cable_hint)

        line = QHBoxLayout()
        line.setSpacing(8)
        self.install_btn = QPushButton("Установить автоматически")
        self.install_btn.setToolTip(
            "Приложение само скачает и поставит драйвер VB-CABLE. "
            "Windows попросит права администратора."
        )
        self.install_btn.clicked.connect(self._install_cable)
        line.addWidget(self.install_btn)

        manual = QPushButton("Скачать вручную")
        manual.setObjectName("Ghost")
        manual.clicked.connect(lambda: webbrowser.open(VB_DOWNLOAD))
        line.addWidget(manual)
        line.addStretch(1)
        box.addLayout(line)

        self.install_progress = QProgressBar()
        self.install_progress.setVisible(False)
        self.install_progress.setTextVisible(True)
        self.install_progress.setStyleSheet(
            f"QProgressBar {{ background: {theme.BG}; border: 1px solid {theme.BORDER};"
            f" border-radius: 8px; height: 20px; text-align: center; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f" stop:0 {theme.ACCENT_2}, stop:1 {theme.ACCENT}); border-radius: 7px; }}"
        )
        box.addWidget(self.install_progress)

        self._update_cable_badge()
        return card

    # ------------------------------------------------------ установка кабеля
    def _install_cable(self) -> None:
        if self._installer is not None and self._installer.isRunning():
            return
        if self.ctx.engine.running:
            self.ctx.engine.stop()   # драйвер не поставить, пока занято аудио
        self.install_btn.setEnabled(False)
        self.install_progress.setVisible(True)
        self.install_progress.setValue(0)

        self._installer = CableInstaller(silent=True, parent=self)
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finished_ok.connect(self._on_installed)
        self._installer.failed.connect(self._on_install_failed)
        self._installer.start()

    def _on_install_progress(self, percent: int, message: str) -> None:
        self.install_progress.setValue(percent)
        self.install_progress.setFormat(message)

    def _on_installed(self, needs_reboot: bool, message: str) -> None:
        self.install_btn.setEnabled(True)
        self.install_progress.setVisible(False)
        devices.refresh_backend()
        changed = devices.autoconfigure(self.ctx.cfg.audio)
        self.ctx.save_and_apply()
        self.reload_devices()
        if changed:
            message += "  ·  выбрано само: " + ", ".join(changed)
        self.ctx.notify(message, not needs_reboot)

    def _on_install_failed(self, message: str) -> None:
        self.install_btn.setEnabled(True)
        self.install_progress.setVisible(False)
        self.ctx.notify("Установка не удалась: " + message, False)

    # ------------------------------------------------------------ действия
    def reload_values(self) -> None:
        """Подтянуть значения из настроек — например, после смены профиля."""
        self.delay.set_value(self.ctx.cfg.mute.delay_ms, silent=True)
        self.block.set_value(self.ctx.cfg.audio.blocksize, silent=True)
        self.in_gain.set_value(int(self.ctx.cfg.audio.input_gain_db), silent=True)
        self.out_gain.set_value(int(self.ctx.cfg.audio.output_gain_db), silent=True)
        self.gate_threshold.set_value(int(self.ctx.cfg.audio.gate_threshold_db), silent=True)
        self.gate_release.set_value(self.ctx.cfg.audio.gate_release_ms, silent=True)
        self._update_delay_note(self.ctx.cfg.mute.delay_ms)

    def _open_calibration(self) -> None:
        from app.ui.calibration_dialog import CalibrationDialog

        CalibrationDialog(self.ctx, self.window()).exec()
        self.reload_values()

    def _set(self, field: str, value) -> None:
        setattr(self.ctx.cfg.audio, field, value)
        self.ctx.save_and_apply()

    def _set_delay(self, value: int) -> None:
        self.ctx.cfg.mute.delay_ms = value
        self._update_delay_note(value)
        self.ctx.save_and_apply()

    def _update_delay_note(self, value: int) -> None:
        if value < 250:
            text, color = "Рискованно: часть мата будет проскакивать в эфир.", theme.DANGER
        elif value < 700:
            text, color = "Хороший баланс для живого разговора.", theme.OK
        elif value < 1200:
            text, color = "Надёжно, но собеседники заметят паузу.", theme.WARN
        else:
            text, color = "Очень надёжно; для обычного общения слишком медленно.", theme.WARN
        self.delay_note.setText(text)
        self.delay_note.setStyleSheet(f"color: {color};")

    def reload_devices(self) -> None:
        cfg = self.ctx.cfg.audio
        self.input_combo.fill(devices.inputs(), cfg.input_device)
        self.output_combo.fill(devices.outputs(), cfg.output_device, VB_HINTS)
        self.monitor_combo.fill(devices.outputs(), cfg.monitor_device)
        self._update_cable_badge()

    def _autoselect(self) -> None:
        cfg = self.ctx.cfg.audio
        default_in = devices.default_input()
        if default_in is not None:
            cfg.input_device = default_in
        cable = devices.find_virtual_cable()
        if cable is not None:
            cfg.output_device = cable.index
            self.ctx.notify(f"Выбран кабель: {cable.name}", True)
        else:
            self.ctx.notify("Виртуальный кабель не найден — установите VB-Cable", False)
        self.ctx.save_and_apply()
        self.reload_devices()

    def _update_cable_badge(self) -> None:
        if not hasattr(self, "cable_badge"):
            return   # карточка кабеля ещё не собрана
        cable = devices.find_virtual_cable()
        if cable is not None:
            self.cable_badge.set_state("установлен: " + cable.name, theme.OK)
            self.cable_hint.setText(
                "Всё готово. В Дискорде или OBS выберите микрофоном CABLE Output — "
                "туда приложение отдаёт очищенный звук."
            )
        else:
            self.cable_badge.set_state("виртуальный микрофон не установлен", theme.WARN)
            self.cable_hint.setText(
                "Нажмите «Установить автоматически» — приложение само скачает драйвер "
                "VB-CABLE и поставит его. Windows попросит права администратора, "
                "иногда нужна перезагрузка. После этого в Дискорде выберите "
                "микрофоном CABLE Output."
            )

    def refresh(self) -> None:
        self.reload_devices()
