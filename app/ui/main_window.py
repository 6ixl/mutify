# -*- coding: utf-8 -*-
"""Главное окно: боковое меню, страницы, трей, горячие клавиши."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget
)

from app.audio import devices
from app.audio.engine import AudioEngine
from app.branding import APP_NAME, APP_TAGLINE, APP_TITLE
from app.config import AppConfig
from app.filter.matcher import ProfanityMatcher
from app.filter.wordlist import WordList
from app.profiles import ProfileStore
from app.stats import Stats
from app.stt.vosk_engine import VoskSTT
from app.system.hotkey import GlobalHotkey
from app.ui import theme
from app.ui.icon import app_icon
from app.ui.pages.ai import AIPage
from app.ui.pages.audio import AudioPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.general import GeneralPage
from app.ui.pages.sounds import SoundsPage
from app.ui.pages.words import WordsPage
from app.ui.tray import Tray


class Toast(QFrame):
    """Всплывающая плашка с сообщением в правом нижнем углу."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedHeight(46)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addWidget(self.label)
        self.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)

    def show_message(self, text: str, ok: bool = True) -> None:
        color = theme.OK if ok else theme.DANGER
        self.setStyleSheet(
            f"background: {theme.CARD}; border: 1px solid {color};"
            f"border-radius: 11px;"
        )
        self.label.setStyleSheet(f"color: {color}; font-size: 12px; border: none;")
        self.label.setText(text)
        self.adjustSize()
        self.setFixedWidth(max(260, min(460, self.label.sizeHint().width() + 46)))
        self._reposition()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(3600)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(350)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(parent.width() - self.width() - 26, parent.height() - self.height() - 22)


class MainWindow(QWidget):
    NAV = (
        ("Мут", "dashboard"),
        ("Словарь", "words"),
        ("Заглушение", "sounds"),
        ("Модель ИИ", "ai"),
        ("Аудио", "audio"),
        ("Программа", "general"),
    )

    def __init__(self, start_in_tray: bool = False) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1080, 780)
        self.setMinimumSize(880, 560)

        # ---- состояние приложения ----
        self.cfg = AppConfig.load()
        # Путь мог остаться от прошлой установки или от перенесённой папки.
        resolved = VoskSTT.resolve_model_path(self.cfg.ai.model_path)
        if resolved != self.cfg.ai.model_path:
            self.cfg.ai.model_path = resolved
            self.cfg.save()

        # Устройства подбираются сами: выбирать руками ничего не нужно.
        self.auto_devices = devices.autoconfigure(self.cfg.audio)
        if self.auto_devices:
            self.cfg.save()

        self.wordlist = WordList.load()
        self.matcher = ProfanityMatcher(self.wordlist, self.cfg.ai)
        self.engine = AudioEngine(self.cfg, self.matcher)
        self.profiles = ProfileStore()
        self.stats = Stats()
        self.hotkey_failures: list[str] = []
        self._quitting = False

        self.setStyleSheet(theme.stylesheet(self.cfg.ui.accent, self.cfg.ui.accent_2))
        self._build()

        self.toast = Toast(self)
        self._shortcuts()
        self._setup_tray()
        self.apply_hotkeys()

        self.engine.mute_state.connect(self._sync_tray)
        self.engine.status.connect(lambda *_: self._sync_tray())
        self.engine.profanity.connect(self._on_profanity_notify)
        self.engine.profanity.connect(lambda word, _rule: self._count_word(word))

        if self.auto_devices:
            QTimer.singleShot(
                400,
                lambda: self.notify(
                    "Подобрано автоматически — " + ", ".join(self.auto_devices), True
                ),
            )
        if self.cfg.general.autostart_mute:
            QTimer.singleShot(900, self._autostart_mute)
        if start_in_tray:
            QTimer.singleShot(0, self.hide)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(self),
            "words": WordsPage(self),
            "sounds": SoundsPage(self),
            "ai": AIPage(self),
            "audio": AudioPage(self),
            "general": GeneralPage(self),
        }
        for _, key in self.NAV:
            self.stack.addWidget(self.pages[key])
        root.addWidget(self.stack, 1)

    def _sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(208)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)

        logo = QLabel(APP_NAME)
        logo.setObjectName("Logo")
        layout.addWidget(logo)
        sub = QLabel(APP_TAGLINE.upper())
        sub.setObjectName("LogoSub")
        layout.addWidget(sub)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (label, key) in enumerate(self.NAV):
            button = QPushButton(label)
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _, i=index: self._go(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)

        layout.addStretch(1)

        self.side_state = QLabel("остановлено")
        self.side_state.setObjectName("Hint")
        self.side_state.setContentsMargins(20, 0, 16, 6)
        self.side_state.setWordWrap(True)
        layout.addWidget(self.side_state)

        self.side_hotkey = QLabel()
        self.side_hotkey.setObjectName("Hint")
        self.side_hotkey.setContentsMargins(20, 0, 16, 0)
        self.side_hotkey.setWordWrap(True)
        layout.addWidget(self.side_hotkey)

        self.engine_state_timer = QTimer(self)
        self.engine_state_timer.timeout.connect(self._update_side_state)
        self.engine_state_timer.start(700)
        return bar

    # ------------------------------------------------------- трей и клавиши
    def _setup_tray(self) -> None:
        self.tray = Tray(self)
        self.tray.show_window.connect(self._restore_window)
        self.tray.toggle_run.connect(self._toggle_run)
        self.tray.toggle_panic.connect(self._toggle_panic)
        self.tray.quit_app.connect(self.quit)
        self._sync_tray()

    def _shortcuts(self) -> None:
        # Дублируют глобальные клавиши, когда окно в фокусе.
        QShortcut(QKeySequence("F8"), self).activated.connect(self._toggle_panic)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.quit)

    def apply_hotkeys(self) -> None:
        """Перерегистрировать глобальные клавиши по текущим настройкам."""
        if not hasattr(self, "hotkeys"):
            self.hotkeys = GlobalHotkey(self)
            self.hotkeys.install(QApplication.instance())
            self.hotkeys.triggered.connect(self._on_hotkey)

        self.hotkeys.unregister_all()
        self.hotkey_failures = []
        general = self.cfg.general
        if not general.hotkey_enabled:
            self.side_hotkey.setText("горячие клавиши выключены")
            return

        for action, combo in (("panic", general.hotkey_panic),
                              ("toggle", general.hotkey_toggle)):
            if combo and not self.hotkeys.register(action, combo):
                self.hotkey_failures.append(combo)
        self.side_hotkey.setText(f"{general.hotkey_panic} — мгновенный мут")
        if self.hotkey_failures:
            self.notify(
                "Клавишу занял кто-то другой: " + ", ".join(self.hotkey_failures), False
            )

    def _on_hotkey(self, action: str) -> None:
        if action == "panic":
            self._toggle_panic()
        elif action == "toggle":
            self._toggle_run()

    # ------------------------------------------------------------- действия
    def _go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()
        elif hasattr(page, "reload"):
            page.reload()

    def go_to(self, key: str) -> None:
        """Переключиться на страницу по имени из бокового меню."""
        for index, (_, name) in enumerate(self.NAV):
            if name == key:
                self.nav_group.button(index).setChecked(True)
                self._go(index)
                return

    def _toggle_run(self) -> None:
        was_running = self.engine.running
        self.pages["dashboard"]._toggle_run()
        if not was_running and self.engine.running:
            self.stats.start_session()
        self._sync_tray()

    def _toggle_panic(self) -> None:
        button = self.pages["dashboard"].panic_btn
        button.setChecked(not button.isChecked())
        self._sync_tray()

    def _autostart_mute(self) -> None:
        if not self.engine.running:
            self.pages["dashboard"]._toggle_run()

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self) -> None:
        self._quitting = True
        self.stats.save(force=True)
        self.engine.stop()
        if hasattr(self, "hotkeys"):
            self.hotkeys.unregister_all()
        self.tray.hide()
        self.cfg.save()
        QApplication.instance().quit()

    # ------------------------------------------------------------ состояние
    def _count_word(self, word: str) -> None:
        self.stats.add_word(word)
        self._sync_tray()

    def _sync_tray(self, *_) -> None:
        if hasattr(self, "tray"):
            self.tray.update_state(
                self.engine.running,
                self.engine.manual_mute,
                self.stats.session_events,
                self.stats.total_events,
            )

    def _on_profanity_notify(self, word: str, rule: str) -> None:
        if self.cfg.general.tray_notifications and not self.isVisible():
            self.tray.notify(APP_NAME, f"Заглушено: {word}")

    def _update_side_state(self) -> None:
        if self.engine.manual_mute:
            self.side_state.setText("ручной мут")
            color = theme.DANGER
        elif self.engine.running:
            self.side_state.setText("в эфире")
            color = theme.OK
        else:
            self.side_state.setText("остановлено")
            color = theme.TEXT_MUTED
        self.side_state.setStyleSheet(f"color: {color}; font-size: 11px;")

    # ------------------------------------------------ контекст для страниц
    @property
    def ctx(self):
        return self

    def notify(self, message: str, ok: bool = True) -> None:
        if self.isVisible():
            self.toast.show_message(message, ok)
        elif self.cfg.general.tray_notifications and hasattr(self, "tray"):
            self.tray.notify(APP_NAME, message)

    def save_and_apply(self) -> None:
        """Сохранить настройки и применить их на лету, без перезапуска мута."""
        self.cfg.save()
        self.matcher.refresh()
        self.engine.reload_sound()

    def reload_settings_pages(self) -> None:
        """Обновить страницы после смены профиля: ползунки должны показать новые значения."""
        for key in ("sounds", "ai", "audio"):
            page = self.pages.get(key)
            if page is None:
                continue
            if hasattr(page, "reload_values"):
                page.reload_values()

    def model_state(self) -> tuple[bool, str]:
        if self.cfg.ai.engine == "whisper":
            from app.stt.whisper_engine import WhisperSTT

            ok, info = WhisperSTT.is_available()
            return ok, ("whisper " + self.cfg.ai.whisper_model) if ok else info
        ok, info = VoskSTT.is_available()
        return ok, info

    # ------------------------------------------------------------ события
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast._reposition()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (event.type() == event.Type.WindowStateChange
                and self.isMinimized()
                and self.cfg.general.minimize_to_tray):
            QTimer.singleShot(0, self.hide)

    def closeEvent(self, event) -> None:
        if not self._quitting and self.cfg.general.close_to_tray:
            # Мут продолжает работать, окно просто прячется.
            event.ignore()
            self.hide()
            if self.cfg.general.tray_notifications:
                self.tray.notify(
                    APP_NAME,
                    "Работаю в фоне. Значок у часов — управление и выход.",
                )
            return
        self._quitting = True
        self.stats.save(force=True)
        self.engine.stop()
        if hasattr(self, "hotkeys"):
            self.hotkeys.unregister_all()
        self.tray.hide()
        self.cfg.save()
        super().closeEvent(event)
