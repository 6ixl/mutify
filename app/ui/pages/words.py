# -*- coding: utf-8 -*-
"""Страница словаря: какие слова глушить, а какие пропускать."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTabWidget, QVBoxLayout, QWidget
)

from app.ui import theme
from app.ui.widgets import Card

KINDS = {
    "roots": (
        "Корни",
        "Ловят все словоформы сразу: корень «пизд» перехватит и «пиздец», и «пизданутый».",
    ),
    "exact": (
        "Точные слова",
        "Глушатся только целиком совпавшие слова. Подходит для мягких словечек.",
    ),
    "allow": (
        "Исключения",
        "Слова, которые никогда не глушатся, даже если похожи на мат: «страхуй», «мудрость».",
    ),
}


class WordListTab(QWidget):
    def __init__(self, ctx, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.kind = kind

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        hint = QLabel(KINDS[kind][1])
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        add_line = QHBoxLayout()
        add_line.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Новое слово и Enter")
        self.input.returnPressed.connect(self._add)
        add_line.addWidget(self.input, 1)
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add)
        add_line.addWidget(add_btn)
        layout.addLayout(add_line)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по списку")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list, 1)

        controls = QHBoxLayout()
        remove = QPushButton("Удалить выбранное")
        remove.setObjectName("Ghost")
        remove.clicked.connect(self._remove)
        controls.addWidget(remove)
        controls.addStretch(1)
        self.counter = QLabel()
        self.counter.setObjectName("Hint")
        controls.addWidget(self.counter)
        layout.addLayout(controls)

        self.reload()

    def reload(self) -> None:
        wl = self.ctx.wordlist
        self.list.blockSignals(True)
        self.list.clear()
        for word in sorted(getattr(wl, self.kind)):
            item = QListWidgetItem(word)
            if self.kind != "allow":
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Unchecked if word in wl.disabled else Qt.Checked
                )
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.counter.setText(f"всего: {self.list.count()}")
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _add(self) -> None:
        word = self.input.text().strip().lower()
        if not word:
            return
        if self.ctx.wordlist.add(self.kind, word):
            self.input.clear()
            self.ctx.matcher.refresh()
            self.reload()
            self.ctx.notify(f"Добавлено: {word}", True)
        else:
            self.ctx.notify("Такое слово уже есть", False)

    def _remove(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.ctx.wordlist.remove(self.kind, item.text())
        self.ctx.matcher.refresh()
        self.reload()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        self.ctx.wordlist.toggle(item.text(), item.checkState() == Qt.Checked)
        self.ctx.matcher.refresh()


class WordsPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Словарь")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Галочка выключает слово, не удаляя его. Изменения применяются сразу, "
            "перезапуск не нужен."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        card = Card()
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; }}"
            f"QTabBar::tab {{ background: transparent; padding: 9px 18px;"
            f" color: {theme.TEXT_DIM}; border-bottom: 2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color: {theme.ACCENT};"
            f" border-bottom: 2px solid {theme.ACCENT}; font-weight: 700; }}"
        )
        self.tabs_by_kind = {}
        for kind, (label, _) in KINDS.items():
            tab = WordListTab(ctx, kind)
            self.tabs_by_kind[kind] = tab
            self.tabs.addTab(tab, label)
        card.add(self.tabs)
        root.addWidget(card, 1)

        root.addWidget(self._test_card())

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        reset = QPushButton("Сбросить к стандартному словарю")
        reset.setObjectName("Ghost")
        reset.clicked.connect(self._reset)
        bottom.addWidget(reset)
        root.addLayout(bottom)

    def _test_card(self) -> Card:
        card = Card("Проверка фразы", "Впишите фразу и посмотрите, что будет заглушено.")
        line = QHBoxLayout()
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("например: да ты заебал уже")
        self.test_input.textChanged.connect(self._test)
        line.addWidget(self.test_input, 1)
        card.add_layout(line)

        self.test_result = QLabel("—")
        self.test_result.setWordWrap(True)
        card.add(self.test_result)
        return card

    def _test(self, text: str) -> None:
        if not text.strip():
            self.test_result.setText("—")
            return
        parts = []
        for word in text.split():
            match = self.ctx.matcher.check(word)
            if match is None:
                parts.append(f'<span style="color:{theme.TEXT_DIM}">{word}</span>')
            else:
                parts.append(
                    f'<span style="color:{theme.DANGER};font-weight:700">'
                    f"[{word}]</span>"
                )
        self.test_result.setText(" ".join(parts))

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Сброс словаря",
            "Вернуть стандартный список и потерять свои добавления?",
        )
        if answer != QMessageBox.Yes:
            return
        self.ctx.wordlist.reset_defaults()
        self.ctx.matcher.refresh()
        self.reload()
        self.ctx.notify("Словарь сброшен", True)

    def reload(self) -> None:
        for tab in self.tabs_by_kind.values():
            tab.reload()
