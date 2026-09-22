# -*- coding: utf-8 -*-
"""Страница ИИ: выбор модели, скорость проверки и строгость решения."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget
)

from app.stt import factory
from app.stt.downloader import CATALOG, ModelDownloader
from app.stt.vosk_engine import VoskSTT
from app.ui import theme
from app.ui.widgets import Badge, Card, FlowLayout, Row, SliderRow, ToggleSwitch


class AIPage(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._downloader = None

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

        title = QLabel("Модель ИИ")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Модель работает полностью локально, без интернета. Ничего никуда не отправляется."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._engine_card())
        root.addWidget(self._model_card())
        root.addWidget(self._speed_card())
        root.addWidget(self._strictness_card())
        root.addWidget(self._whisper_card())
        root.addStretch(1)
        self.refresh()

    # ------------------------------------------------------------ движок
    def _engine_card(self) -> Card:
        card = Card("Движок распознавания")
        box = card.body()

        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Vosk — быстрый, процессор", "vosk")
        self.engine_combo.addItem("faster-whisper — точный, видеокарта", "whisper")
        index = self.engine_combo.findData(self.ctx.cfg.ai.engine)
        self.engine_combo.setCurrentIndex(max(0, index))
        self.engine_combo.currentIndexChanged.connect(self._set_engine)
        box.addWidget(
            Row(
                "Движок",
                self.engine_combo,
                "Vosk успевает вырезать мат при задержке 400 мс. "
                "Whisper точнее, но требует задержки от 800 мс.",
            )
        )

        badges = FlowLayout(spacing=8)
        self.vosk_badge = Badge("Vosk")
        self.whisper_badge = Badge("Whisper")
        badges.addWidget(self.vosk_badge)
        badges.addWidget(self.whisper_badge)
        box.addLayout(badges)
        return card

    # ------------------------------------------------------------ модель
    def _model_card(self) -> Card:
        card = Card("Модель Vosk", "Скачивается один раз и дальше работает офлайн.")
        box = card.body()

        self.model_label = QLabel()
        self.model_label.setObjectName("Hint")
        self.model_label.setWordWrap(True)
        box.addWidget(self.model_label)

        self.catalog_combo = QComboBox()
        for key, entry in CATALOG.items():
            self.catalog_combo.addItem(entry["title"], key)
        box.addWidget(Row("Какую скачать", self.catalog_combo))

        self.catalog_hint = QLabel()
        self.catalog_hint.setObjectName("Hint")
        self.catalog_hint.setWordWrap(True)
        self.catalog_combo.currentIndexChanged.connect(self._update_catalog_hint)
        box.addWidget(self.catalog_hint)
        self._update_catalog_hint()

        line = QHBoxLayout()
        line.setSpacing(8)
        self.download_btn = QPushButton("Скачать модель")
        self.download_btn.clicked.connect(self._download)
        line.addWidget(self.download_btn)

        browse = QPushButton("Указать папку вручную...")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse_model)
        line.addWidget(browse)
        line.addStretch(1)
        box.addLayout(line)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {theme.BG}; border: 1px solid {theme.BORDER};"
            f" border-radius: 8px; height: 20px; text-align: center; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f" stop:0 {theme.ACCENT_2}, stop:1 {theme.ACCENT}); border-radius: 7px; }}"
        )
        box.addWidget(self.progress)
        return card

    # ------------------------------------------------------------ скорость
    def _speed_card(self) -> Card:
        ai = self.ctx.cfg.ai
        card = Card(
            "Скорость проверки",
            "Насколько мелкими порциями модель получает звук. "
            "Меньше порция — быстрее реакция, выше нагрузка на процессор.",
        )
        box = card.body()

        self.chunk = SliderRow(
            "Порция звука", 32, 480, ai.chunk_ms, " мс",
            "32-96 мс: мгновенная реакция. 200+ мс: экономия процессора, реакция медленнее.",
            step=16,
        )
        self.chunk.changed.connect(lambda v: self._set("chunk_ms", v))
        box.addWidget(self.chunk)

        self.partial = ToggleSwitch()
        self.partial.setChecked(ai.react_on_partial)
        self.partial.toggled.connect(lambda v: self._set("react_on_partial", v))
        box.addWidget(
            Row(
                "Реагировать на промежуточный результат",
                self.partial,
                "Глушить, как только модель догадалась о слове, не дожидаясь конца фразы. "
                "Это главный источник скорости — выключайте только при ложных срабатываниях.",
            )
        )

        self.threads = SliderRow(
            "Потоков процессора", 1, 16, ai.max_cpu_threads, "",
            "Для Ryzen 5 8400F оптимально 4-6.",
        )
        self.threads.changed.connect(lambda v: self._set("max_cpu_threads", v))
        box.addWidget(self.threads)
        return card

    # ------------------------------------------------------------ строгость
    def _strictness_card(self) -> Card:
        ai = self.ctx.cfg.ai
        card = Card(
            "Строгость решения",
            "Насколько долго модель обдумывает слово перед тем, как признать его матом.",
        )
        box = card.body()

        self.confidence = SliderRow(
            "Порог уверенности", 0, 100, int(ai.confidence * 100), " %",
            "Ниже порога слово считается расслышанным неточно и пропускается. "
            "Выше значение — меньше ложных срабатываний, но мат может проскочить.",
        )
        self.confidence.changed.connect(lambda v: self._set("confidence", v / 100.0))
        box.addWidget(self.confidence)

        self.roots = ToggleSwitch()
        self.roots.setChecked(ai.root_matching)
        self.roots.toggled.connect(lambda v: self._set("root_matching", v))
        box.addWidget(
            Row("Ловить по корню слова", self.roots,
                "Перехватывает любые формы и приставки: «недоебал», «запиздел».")
        )

        self.fuzzy = ToggleSwitch()
        self.fuzzy.setChecked(ai.fuzzy)
        self.fuzzy.toggled.connect(self._toggle_fuzzy)
        box.addWidget(
            Row("Нечёткое совпадение", self.fuzzy,
                "Ловит слова, которые модель расслышала с ошибкой: «пиздетс», «бляц».")
        )

        self.fuzzy_threshold = SliderRow(
            "Порог похожести", 50, 100, int(ai.fuzzy_threshold * 100), " %",
            "Ниже 75 % начнёт глушить обычные слова. Разумный диапазон — 80-90 %.",
        )
        self.fuzzy_threshold.changed.connect(
            lambda v: self._set("fuzzy_threshold", v / 100.0)
        )
        self.fuzzy_threshold.setEnabled(ai.fuzzy)
        box.addWidget(self.fuzzy_threshold)
        return card

    # ------------------------------------------------------------ whisper
    def _whisper_card(self) -> Card:
        ai = self.ctx.cfg.ai
        card = Card(
            "Настройки faster-whisper",
            "Применяются, только когда выбран движок Whisper.",
        )
        box = card.body()

        self.whisper_model = QComboBox()
        for name in ("tiny", "base", "small", "medium", "large-v3"):
            self.whisper_model.addItem(name, name)
        index = self.whisper_model.findData(ai.whisper_model)
        self.whisper_model.setCurrentIndex(max(0, index))
        self.whisper_model.currentIndexChanged.connect(
            lambda: self._set("whisper_model", self.whisper_model.currentData())
        )
        box.addWidget(
            Row("Размер модели", self.whisper_model,
                "Для RTX 5060 Ti 16 ГБ комфортны small и medium; large-v3 тоже влезет, "
                "но задержка вырастет.")
        )

        self.whisper_device = QComboBox()
        self.whisper_device.addItem("Видеокарта (CUDA)", "cuda")
        self.whisper_device.addItem("Процессор", "cpu")
        index = self.whisper_device.findData(ai.whisper_device)
        self.whisper_device.setCurrentIndex(max(0, index))
        self.whisper_device.currentIndexChanged.connect(
            lambda: self._set("whisper_device", self.whisper_device.currentData())
        )
        box.addWidget(Row("Считать на", self.whisper_device))

        self.whisper_window = SliderRow(
            "Окно обдумывания", 300, 3000, ai.whisper_window_ms, " мс",
            "Сколько звука Whisper анализирует за один проход. "
            "Задержку мута ставьте не меньше этого значения.",
            step=50,
        )
        self.whisper_window.changed.connect(lambda v: self._set("whisper_window_ms", v))
        box.addWidget(self.whisper_window)

        install = QLabel(
            "Если движок недоступен, установите его командой:  pip install faster-whisper"
        )
        install.setObjectName("Hint")
        install.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(install)
        return card

    # ------------------------------------------------------------ действия
    def reload_values(self) -> None:
        """Подтянуть значения из настроек — например, после смены профиля."""
        ai = self.ctx.cfg.ai
        self.chunk.set_value(ai.chunk_ms, silent=True)
        self.threads.set_value(ai.max_cpu_threads, silent=True)
        self.confidence.set_value(int(ai.confidence * 100), silent=True)
        self.fuzzy_threshold.set_value(int(ai.fuzzy_threshold * 100), silent=True)
        self.whisper_window.set_value(ai.whisper_window_ms, silent=True)
        for toggle, value in ((self.partial, ai.react_on_partial),
                              (self.roots, ai.root_matching),
                              (self.fuzzy, ai.fuzzy)):
            toggle.blockSignals(True)
            toggle.setChecked(value)
            toggle.blockSignals(False)
        self.fuzzy_threshold.setEnabled(ai.fuzzy)
        index = self.engine_combo.findData(ai.engine)
        if index >= 0:
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentIndex(index)
            self.engine_combo.blockSignals(False)
        self.refresh()

    def _set(self, field: str, value) -> None:
        setattr(self.ctx.cfg.ai, field, value)
        self.ctx.save_and_apply()

    def _toggle_fuzzy(self, enabled: bool) -> None:
        self._set("fuzzy", enabled)
        self.fuzzy_threshold.setEnabled(enabled)

    def _set_engine(self) -> None:
        self._set("engine", self.engine_combo.currentData())
        if self.ctx.engine.running:
            self.ctx.notify("Движок сменится после перезапуска мута", False)

    def _update_catalog_hint(self) -> None:
        key = self.catalog_combo.currentData()
        self.catalog_hint.setText(CATALOG[key]["hint"])

    def _browse_model(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка модели Vosk")
        if path:
            self._set("model_path", path)
            self.refresh()

    def _download(self) -> None:
        if self._downloader is not None and self._downloader.isRunning():
            return
        key = self.catalog_combo.currentData()
        self.download_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self._downloader = ModelDownloader(key, self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.finished_ok.connect(self._on_downloaded)
        self._downloader.failed.connect(self._on_failed)
        self._downloader.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.progress.setFormat(message)

    def _on_downloaded(self, path: str) -> None:
        self._set("model_path", path)
        self.download_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.ctx.notify("Модель готова к работе", True)
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.ctx.notify(f"Не удалось скачать модель: {message}", False)

    def refresh(self) -> None:
        available = factory.availability()
        for key, badge in (("vosk", self.vosk_badge), ("whisper", self.whisper_badge)):
            ok, info = available[key]
            name = "Vosk" if key == "vosk" else "Whisper"
            badge.set_state(
                f"{name}: {info}", theme.OK if ok else theme.WARN
            )

        path = self.ctx.cfg.ai.model_path or VoskSTT.autodetect_model()
        if path:
            self.model_label.setText(f"Текущая модель: {path}")
        else:
            self.model_label.setText(
                "Модель не найдена. Нажмите «Скачать модель» — она встанет в папку models/."
            )
