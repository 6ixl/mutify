# -*- coding: utf-8 -*-
"""Страница «Программа»: автозапуск, трей, горячие клавиши."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget
)

from app.branding import APP_NAME, APP_TAGLINE, APP_VERSION
from app.paths import DATA_DIR
from app.system import autostart
from app.ui import theme
from app.ui.icon import draw_logo
from app.ui.widgets import Badge, Card, Row, ToggleSwitch


class GeneralPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

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

        title = QLabel("Программа")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel("Как приложение ведёт себя в системе.")
        hint.setObjectName("PageHint")
        root.addWidget(hint)

        root.addWidget(self._startup_card())
        root.addWidget(self._tray_card())
        root.addWidget(self._hotkey_card())
        root.addWidget(self._reset_card())
        root.addWidget(self._about_card())
        root.addStretch(1)

    # ------------------------------------------------------------ автозапуск
    def _startup_card(self) -> Card:
        general = self.ctx.cfg.general
        card = Card("Запуск")
        box = card.body()

        self.autostart_toggle = ToggleSwitch()
        self.autostart_toggle.setChecked(autostart.is_enabled())
        self.autostart_toggle.toggled.connect(self._set_autostart)
        box.addWidget(
            Row("Запускать вместе с Windows", self.autostart_toggle,
                "Приложение стартует свёрнутым в трей при входе в систему.")
        )

        self.automute_toggle = ToggleSwitch()
        self.automute_toggle.setChecked(general.autostart_mute)
        self.automute_toggle.toggled.connect(
            lambda v: self._set("autostart_mute", v)
        )
        box.addWidget(
            Row("Включать мут сразу при запуске", self.automute_toggle,
                "Не нужно каждый раз нажимать «Запустить» — фильтр включится сам.")
        )
        return card

    # ------------------------------------------------------------------ трей
    def _tray_card(self) -> Card:
        general = self.ctx.cfg.general
        card = Card("Системный трей", "Значок у часов: мут под рукой, окно не мешает.")
        box = card.body()

        self.minimize_toggle = ToggleSwitch()
        self.minimize_toggle.setChecked(general.minimize_to_tray)
        self.minimize_toggle.toggled.connect(lambda v: self._set("minimize_to_tray", v))
        box.addWidget(Row("Сворачивать в трей", self.minimize_toggle))

        self.close_toggle = ToggleSwitch()
        self.close_toggle.setChecked(general.close_to_tray)
        self.close_toggle.toggled.connect(lambda v: self._set("close_to_tray", v))
        box.addWidget(
            Row("Крестик прячет в трей", self.close_toggle,
                "Мут продолжит работать. Полностью выйти можно из меню значка.")
        )

        self.notify_toggle = ToggleSwitch()
        self.notify_toggle.setChecked(general.tray_notifications)
        self.notify_toggle.toggled.connect(lambda v: self._set("tray_notifications", v))
        box.addWidget(Row("Всплывающие уведомления", self.notify_toggle))
        return card

    # ------------------------------------------------------- горячие клавиши
    def _hotkey_card(self) -> Card:
        general = self.ctx.cfg.general
        card = Card(
            "Горячие клавиши",
            "Работают поверх любой игры и программы, окно открывать не нужно.",
        )
        box = card.body()

        self.hotkey_toggle = ToggleSwitch()
        self.hotkey_toggle.setChecked(general.hotkey_enabled)
        self.hotkey_toggle.toggled.connect(self._set_hotkeys_enabled)
        box.addWidget(Row("Включить горячие клавиши", self.hotkey_toggle))

        self.panic_input = QLineEdit(general.hotkey_panic)
        self.panic_input.setMaximumWidth(190)
        self.panic_input.editingFinished.connect(
            lambda: self._set_hotkey("hotkey_panic", self.panic_input.text())
        )
        box.addWidget(
            Row("Мгновенная тишина", self.panic_input,
                "Например: F8, Ctrl+Alt+M, Shift+F9. Держать не нужно — нажатие переключает.")
        )

        self.toggle_input = QLineEdit(general.hotkey_toggle)
        self.toggle_input.setMaximumWidth(190)
        self.toggle_input.editingFinished.connect(
            lambda: self._set_hotkey("hotkey_toggle", self.toggle_input.text())
        )
        box.addWidget(Row("Запустить / остановить мут", self.toggle_input))

        self.hotkey_badge = Badge()
        line = QHBoxLayout()
        line.addWidget(self.hotkey_badge)
        line.addStretch(1)
        box.addLayout(line)
        self._update_hotkey_badge()
        return card

    # ----------------------------------------------------------------- сброс
    def _reset_card(self) -> Card:
        card = Card(
            "Сброс",
            "Каждая кнопка сбрасывает только своё — остальное остаётся на месте.",
        )
        box = card.body()

        line = QHBoxLayout()
        line.setSpacing(8)

        settings = QPushButton("Сбросить настройки")
        settings.setToolTip(
            "Звук, задержка, модель, аудио и поведение программы — к заводским"
        )
        settings.clicked.connect(self._reset_settings)
        line.addWidget(settings)

        words = QPushButton("Сбросить словарь")
        words.setObjectName("Ghost")
        words.setToolTip("Вернуть стандартный список слов и потерять свои добавления")
        words.clicked.connect(self._reset_words)
        line.addWidget(words)

        stats = QPushButton("Обнулить счётчик")
        stats.setObjectName("Ghost")
        stats.clicked.connect(self._reset_stats)
        line.addWidget(stats)

        profiles = QPushButton("Удалить свои профили")
        profiles.setObjectName("Ghost")
        profiles.clicked.connect(self._reset_profiles)
        line.addWidget(profiles)

        line.addStretch(1)
        box.addLayout(line)

        note = QLabel(
            "Сброс настроек остановит мут и заново подберёт микрофон и выход. "
            "Свои звуки в папке и скачанная модель остаются."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        box.addWidget(note)
        return card

    def _confirm(self, title: str, question: str) -> bool:
        answer = QMessageBox.question(self, title, question)
        return answer == QMessageBox.Yes

    def _reset_settings(self) -> None:
        if not self._confirm(
            "Сброс настроек",
            "Вернуть все настройки к заводским? Словарь, звуки и статистика останутся.",
        ):
            return
        self.ctx.reset_settings()
        self.refresh()

    def _reset_words(self) -> None:
        if not self._confirm(
            "Сброс словаря",
            "Вернуть стандартный словарь? Свои добавленные слова будут потеряны.",
        ):
            return
        self.ctx.wordlist.reset_defaults()
        self.ctx.matcher.refresh()
        self.ctx.pages["words"].reload()
        self.ctx.notify("Словарь сброшен", True)

    def _reset_stats(self) -> None:
        if not self._confirm("Счётчик", "Обнулить всю статистику перехватов?"):
            return
        self.ctx.stats.reset()
        self.ctx.pages["dashboard"].update_counters()
        self.ctx.notify("Счётчик обнулён", True)

    def _reset_profiles(self) -> None:
        store = self.ctx.profiles
        if not store.custom:
            self.ctx.notify("Своих профилей нет", False)
            return
        if not self._confirm(
            "Профили", f"Удалить свои профили ({len(store.custom)} шт.)?"
        ):
            return
        for name in list(store.custom):
            store.remove(name)
        self.ctx.pages["dashboard"]._reload_profiles()
        self.ctx.notify("Свои профили удалены", True)

    # ----------------------------------------------------------- о программе
    def _about_card(self) -> Card:
        card = Card("О программе")
        box = card.body()

        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(draw_logo(64))
        head.addWidget(logo)

        column = QVBoxLayout()
        column.setSpacing(2)
        name = QLabel(f"{APP_NAME} {APP_VERSION}")
        name.setObjectName("Value")
        column.addWidget(name)
        sub = QLabel(APP_TAGLINE + " · всё считается локально, без интернета")
        sub.setObjectName("Hint")
        column.addWidget(sub)
        head.addLayout(column)
        head.addStretch(1)
        box.addLayout(head)

        line = QHBoxLayout()
        folder = QPushButton("Открыть папку настроек")
        folder.setObjectName("Ghost")
        folder.clicked.connect(self._open_data_dir)
        line.addWidget(folder)
        line.addStretch(1)
        box.addLayout(line)
        return card

    # ------------------------------------------------------------- действия
    def _set(self, field: str, value) -> None:
        setattr(self.ctx.cfg.general, field, value)
        self.ctx.cfg.save()

    def _set_autostart(self, enabled: bool) -> None:
        ok, message = autostart.set_enabled(enabled)
        self.ctx.notify(message, ok)
        if not ok:
            self.autostart_toggle.blockSignals(True)
            self.autostart_toggle.setChecked(not enabled)
            self.autostart_toggle.blockSignals(False)

    def _set_hotkeys_enabled(self, enabled: bool) -> None:
        self._set("hotkey_enabled", enabled)
        self.ctx.apply_hotkeys()
        self._update_hotkey_badge()

    def _set_hotkey(self, field: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        self._set(field, value)
        self.ctx.apply_hotkeys()
        self._update_hotkey_badge()

    def _update_hotkey_badge(self) -> None:
        if not self.ctx.cfg.general.hotkey_enabled:
            self.hotkey_badge.set_state("горячие клавиши выключены", theme.TEXT_MUTED)
            return
        failed = self.ctx.hotkey_failures
        if failed:
            self.hotkey_badge.set_state(
                "занято другой программой: " + ", ".join(failed), theme.WARN
            )
        else:
            self.hotkey_badge.set_state("клавиши зарегистрированы", theme.OK)

    def _open_data_dir(self) -> None:
        try:
            os.startfile(str(DATA_DIR))
        except (OSError, AttributeError):
            subprocess.Popen(["explorer", str(DATA_DIR)])

    def refresh(self) -> None:
        self.autostart_toggle.blockSignals(True)
        self.autostart_toggle.setChecked(autostart.is_enabled())
        self.autostart_toggle.blockSignals(False)
        self._update_hotkey_badge()
