# -*- coding: utf-8 -*-
"""Главная страница: запуск, состояние, живой транскрипт, лента срабатываний."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget
)

from app.audio import devices
from app.ui import theme
from app.ui.widgets import Badge, Card, FlowLayout, LevelMeter, StatusOrb, glow


class DashboardPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._build()
        self._connect()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        # Страница внутри прокрутки: при низком окне карточки не наезжают
        # друг на друга, а появляется полоса прокрутки.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        holder = QWidget()
        scroll.setWidget(holder)
        root = QVBoxLayout(holder)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Живой мут")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Звук с микрофона задерживается на выбранное время, проверяется моделью "
            "и уходит в виртуальный кабель уже без мата."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._profile_card())

        # Две карточки рядом, а на узком окне — друг под другом (см. resizeEvent).
        self.control_card = self._control_card()
        self.stats_card = self._stats_card()
        self._top = QGridLayout()
        self._top.setSpacing(16)
        self._stacked_top = False
        self._top.addWidget(self.control_card, 0, 0)
        self._top.addWidget(self.stats_card, 0, 1)
        root.addLayout(self._top)

        root.addWidget(self._transcript_card())
        root.addWidget(self._events_card(), 1)

    def _profile_card(self) -> Card:
        card = Card("Профиль")
        box = card.body()

        line = QHBoxLayout()
        line.setSpacing(8)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(190)
        self.profile_combo.currentIndexChanged.connect(self._apply_profile)
        line.addWidget(self.profile_combo, 1)

        save_btn = QPushButton("Сохранить как...")
        save_btn.setObjectName("Ghost")
        save_btn.setToolTip("Запомнить текущие настройки как новый профиль")
        save_btn.clicked.connect(self._save_profile)
        line.addWidget(save_btn)

        self.profile_delete = QPushButton("Удалить")
        self.profile_delete.setObjectName("Ghost")
        self.profile_delete.clicked.connect(self._delete_profile)
        line.addWidget(self.profile_delete)
        card.add_layout(line)

        self.profile_hint = QLabel()
        self.profile_hint.setObjectName("Hint")
        self.profile_hint.setWordWrap(True)
        card.add(self.profile_hint)

        self._reload_profiles()
        return card

    def _control_card(self) -> Card:
        card = Card()
        box = card.body()
        box.setSpacing(14)

        self.orb = StatusOrb()
        orb_line = QHBoxLayout()
        orb_line.setContentsMargins(0, 4, 0, 0)
        orb_line.addStretch(1)
        orb_line.addWidget(self.orb)
        orb_line.addStretch(1)
        box.addLayout(orb_line)

        self.state_label = QLabel("Остановлено")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setObjectName("Value")
        self.state_label.setMinimumHeight(22)
        self.state_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        box.addWidget(self.state_label)

        self.start_btn = QPushButton("ЗАПУСТИТЬ")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setMinimumHeight(46)
        glow(self.start_btn, theme.ACCENT, 30)
        box.addWidget(self.start_btn)

        self.panic_btn = QPushButton("ЗАГЛУШИТЬ ВРУЧНУЮ")
        self.panic_btn.setObjectName("Danger")
        self.panic_btn.setCheckable(True)
        self.panic_btn.setCursor(Qt.PointingHandCursor)
        self.panic_btn.setMinimumHeight(44)
        self.panic_btn.setToolTip("Полная тишина в эфире, пока кнопка нажата (или по F8)")
        box.addWidget(self.panic_btn)

        level_line = QHBoxLayout()
        level_line.setSpacing(10)
        mic_label = QLabel("Микрофон")
        mic_label.setObjectName("Hint")
        level_line.addWidget(mic_label)
        self.meter = LevelMeter()
        level_line.addWidget(self.meter, 1)
        box.addLayout(level_line)
        return card

    def _stats_card(self) -> Card:
        card = Card("Состояние")
        box = card.body()

        self.route_label = QLabel()
        self.route_label.setObjectName("Hint")
        self.route_label.setWordWrap(True)
        box.addWidget(self.route_label)

        badges = FlowLayout(spacing=8)
        self.model_badge = Badge("модель")
        self.cable_badge = Badge("кабель")
        self.delay_badge = Badge("задержка")
        for badge in (self.model_badge, self.cable_badge, self.delay_badge):
            badges.addWidget(badge)
        box.addLayout(badges)

        box.addStretch(1)

        numbers = QHBoxLayout()
        numbers.setSpacing(20)
        self.events_value = QLabel("0")
        self.events_value.setObjectName("BigStat")
        self.muted_value = QLabel("0.0 с")
        self.muted_value.setObjectName("BigStat")
        self.total_value = QLabel("0")
        self.total_value.setObjectName("BigStat")
        for value, caption in ((self.events_value, "за сессию"),
                               (self.muted_value, "заглушено"),
                               (self.total_value, "всего")):
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(value)
            label = QLabel(caption)
            label.setObjectName("Hint")
            column.addWidget(label)
            numbers.addLayout(column)
        numbers.addStretch(1)
        box.addLayout(numbers)

        self.top_words_label = QLabel()
        self.top_words_label.setObjectName("Hint")
        self.top_words_label.setWordWrap(True)
        box.addWidget(self.top_words_label)
        return card

    def _transcript_card(self) -> Card:
        card = Card("Что слышит модель")
        self.transcript = QLabel("—")
        self.transcript.setObjectName("Transcript")
        self.transcript.setWordWrap(True)
        self.transcript.setMinimumHeight(52)
        card.add(self.transcript)
        return card

    def _events_card(self) -> Card:
        card = Card("Перехваченные слова")
        self.events = QListWidget()
        self.events.setMinimumHeight(110)
        card.add(self.events)

        line = QHBoxLayout()
        line.addStretch(1)
        clear = QPushButton("Очистить список")
        clear.setObjectName("Ghost")
        clear.clicked.connect(self.events.clear)
        line.addWidget(clear)
        card.add_layout(line)
        return card

    # ------------------------------------------------------------ сигналы
    def _connect(self) -> None:
        engine = self.ctx.engine
        engine.level_changed.connect(self.meter.set_level)
        engine.partial_text.connect(self._on_partial)
        engine.final_text.connect(self._on_final)
        engine.profanity.connect(self._on_profanity)
        engine.mute_state.connect(self._on_mute)
        engine.status.connect(self._on_status)
        engine.stats.connect(self._on_stats)

        self.start_btn.clicked.connect(self._toggle_run)
        self.panic_btn.toggled.connect(self._toggle_panic)

    # ------------------------------------------------------------ действия
    def _toggle_run(self) -> None:
        engine = self.ctx.engine
        if engine.running:
            engine.stop()
            self.refresh()
            return

        # Нечего слушать или некуда отдавать — пробуем подобрать сами.
        from app.audio import devices

        changed = devices.autoconfigure(self.ctx.cfg.audio)
        if changed:
            self.ctx.cfg.save()
            self.ctx.notify("Подобрано автоматически — " + ", ".join(changed), True)

        if self.ctx.cfg.audio.output_device is None:
            self.ctx.notify(
                "Нет виртуального микрофона. Откройте «Аудио» и нажмите "
                "«Установить автоматически»",
                False,
            )
            self.ctx.go_to("audio")
            return

        self.ctx.matcher.refresh()
        engine.start()
        self.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_top(self.width())

    def _relayout_top(self, width: int) -> None:
        """Узкое окно — карточки в столбик, широкое — рядом."""
        needed = (self.control_card.minimumSizeHint().width()
                  + self.stats_card.minimumSizeHint().width() + 16 + 56)
        stacked = width < needed
        if stacked == self._stacked_top:
            return
        self._stacked_top = stacked
        self._top.removeWidget(self.control_card)
        self._top.removeWidget(self.stats_card)
        if stacked:
            self._top.addWidget(self.control_card, 0, 0)
            self._top.addWidget(self.stats_card, 1, 0)
        else:
            self._top.addWidget(self.control_card, 0, 0)
            self._top.addWidget(self.stats_card, 0, 1)

    # ------------------------------------------------------------- профили
    def _reload_profiles(self) -> None:
        store = self.ctx.profiles
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for name in store.names():
            mark = "" if store.is_builtin(name) else "  ·  свой"
            self.profile_combo.addItem(name + mark, name)
        index = self.profile_combo.findData(store.active)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)
        self._update_profile_hint()

    def _update_profile_hint(self) -> None:
        store = self.ctx.profiles
        name = self.profile_combo.currentData()
        if not name:
            return
        hint = store.hint(name)
        if store.detect(self.ctx.cfg) != name:
            hint += "   (настройки изменены вручную)"
        self.profile_hint.setText(hint)
        self.profile_delete.setEnabled(not store.is_builtin(name))

    def _apply_profile(self) -> None:
        store = self.ctx.profiles
        name = self.profile_combo.currentData()
        profile = store.get(name) if name else None
        if profile is None:
            return
        store.apply_to(self.ctx.cfg, name)
        self.ctx.save_and_apply()
        self.ctx.reload_settings_pages()
        self._update_profile_hint()
        self.refresh()
        self.ctx.notify(f"Профиль «{name}» применён", True)

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Новый профиль", "Название профиля:"
        )
        name = name.strip()
        if not ok or not name:
            return
        if self.ctx.profiles.is_builtin(name):
            self.ctx.notify("Так называется встроенный профиль — выберите другое имя", False)
            return
        self.ctx.profiles.save_current(name, self.ctx.cfg)
        self._reload_profiles()
        self.ctx.notify(f"Профиль «{name}» сохранён", True)

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentData()
        if not name or self.ctx.profiles.is_builtin(name):
            return
        answer = QMessageBox.question(self, "Удаление профиля", f"Удалить «{name}»?")
        if answer != QMessageBox.Yes:
            return
        self.ctx.profiles.remove(name)
        self._reload_profiles()

    def _toggle_panic(self, enabled: bool) -> None:
        self.ctx.engine.panic(enabled)
        self.panic_btn.setText("ЭФИР ЗАГЛУШЕН" if enabled else "ЗАГЛУШИТЬ ВРУЧНУЮ")

    # ------------------------------------------------------------ обновление
    def refresh(self) -> None:
        cfg = self.ctx.cfg
        running = self.ctx.engine.running

        self.start_btn.setText("ОСТАНОВИТЬ" if running else "ЗАПУСТИТЬ")
        self.state_label.setText("В эфире" if running else "Остановлено")
        self.orb.set_state(running, self.ctx.engine.manual_mute)

        self.route_label.setText(
            "Вход: {}\nВыход: {}".format(
                devices.describe(cfg.audio.input_device, "input"),
                devices.describe(cfg.audio.output_device, "output"),
            )
        )

        ok, info = self.ctx.model_state()
        self.model_badge.set_state(
            ("модель: " + info) if ok else "модель не готова",
            theme.OK if ok else theme.DANGER,
        )

        cable = devices.find_virtual_cable()
        self.cable_badge.set_state(
            "кабель найден" if cable else "VB-Cable не найден",
            theme.OK if cable else theme.WARN,
        )
        self.delay_badge.set_state(f"задержка {cfg.mute.delay_ms} мс", theme.ACCENT)
        self.update_counters()
        self._update_profile_hint()

    def _on_partial(self, text: str) -> None:
        self.transcript.setText(text or "—")

    def _on_final(self, text: str) -> None:
        if text:
            self.transcript.setText(text)

    def _on_profanity(self, word: str, rule: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        item = QListWidgetItem(f"{stamp}   «{word}»   → заглушено   ({rule})")
        item.setForeground(Qt.red if rule == "exact" else Qt.white)
        self.events.insertItem(0, item)
        while self.events.count() > 200:
            self.events.takeItem(self.events.count() - 1)
        self.update_counters()

    def _on_mute(self, muted: bool) -> None:
        self.orb.set_state(self.ctx.engine.running, muted)
        if self.ctx.engine.running:
            self.state_label.setText("ЗАГЛУШЕНО" if muted else "В эфире")

    def _on_status(self, message: str, ok: bool) -> None:
        self.ctx.notify(message, ok)
        self.refresh()

    def _on_stats(self, events: int, seconds: float) -> None:
        stats = self.ctx.stats
        stats.set_session_seconds(seconds)
        self.events_value.setText(str(stats.session_events))
        self.muted_value.setText(f"{seconds:.1f} с")
        self.total_value.setText(str(stats.total_events))

    def update_counters(self) -> None:
        stats = self.ctx.stats
        self.events_value.setText(str(stats.session_events))
        self.muted_value.setText(f"{stats.session_seconds:.1f} с")
        self.total_value.setText(str(stats.total_events))
        top = stats.top_words(5)
        if top:
            listing = ",   ".join(f"{word} — {count}" for word, count in top)
            self.top_words_label.setText(f"Чаще всего ({stats.since()}):   {listing}")
        else:
            self.top_words_label.setText("Пока ничего не перехвачено.")
