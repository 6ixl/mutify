# -*- coding: utf-8 -*-
"""Значок в системном трее: управление мутом, не открывая окно."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.branding import APP_NAME
from app.ui.icon import app_icon, logo_with_counter


class Tray(QObject):
    show_window = Signal()
    toggle_run = Signal()
    toggle_panic = Signal()
    quit_app = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), parent)
        self.icon.setToolTip(APP_NAME)

        menu = QMenu()
        self.open_action = QAction("Открыть окно", menu)
        self.open_action.triggered.connect(self.show_window.emit)
        menu.addAction(self.open_action)
        menu.addSeparator()

        self.run_action = QAction("Запустить мут", menu)
        self.run_action.triggered.connect(self.toggle_run.emit)
        menu.addAction(self.run_action)

        self.panic_action = QAction("Заглушить эфир", menu)
        self.panic_action.setCheckable(True)
        self.panic_action.triggered.connect(self.toggle_panic.emit)
        menu.addAction(self.panic_action)
        menu.addSeparator()

        self.counter_action = QAction("Перехвачено: 0", menu)
        self.counter_action.setEnabled(False)
        menu.addAction(self.counter_action)
        menu.addSeparator()

        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window.emit()

    # ---------------------------------------------------------- состояние
    def update_state(self, running: bool, muted: bool, session: int = 0,
                     total: int = 0) -> None:
        self.run_action.setText("Остановить мут" if running else "Запустить мут")
        self.panic_action.setChecked(muted)
        if muted:
            state = "эфир заглушен"
        elif running:
            state = "в эфире"
        else:
            state = "остановлено"

        self.counter_action.setText(
            f"Перехвачено: {session} за сессию · {total} всего"
        )
        self.icon.setToolTip(
            "\n".join((
                f"{APP_NAME} — {state}",
                f"Перехвачено за сессию: {session}",
                f"Всего за всё время: {total}",
            ))
        )
        # Перечёркнутый микрофон, когда звук не идёт в эфир, и счётчик в углу.
        self.icon.setIcon(
            QIcon(logo_with_counter(64, session, muted=muted or not running))
        )

    def notify(self, title: str, message: str) -> None:
        self.icon.showMessage(title, message, app_icon(), 2500)

    def hide(self) -> None:
        self.icon.hide()
