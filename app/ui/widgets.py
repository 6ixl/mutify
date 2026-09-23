# -*- coding: utf-8 -*-
"""Самодельные виджеты в неоновом стиле: карточки, тумблеры, индикаторы."""
from __future__ import annotations

from PySide6.QtCore import (
    Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt,
    Signal, QTimer
)
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLayout, QSizePolicy, QSlider, QVBoxLayout, QWidget
)

from app.ui import theme


def glow(widget: QWidget, color: str = theme.ACCENT, radius: int = 28) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(radius)
    effect.setColor(QColor(color))
    effect.setOffset(0, 0)
    widget.setGraphicsEffect(effect)


def hint_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Подсказка под настройкой.

    Перенос по словам плюс небольшая минимальная ширина: иначе длинный текст
    задирает минимальный размер всей карточки, и две колонки перестают
    помещаться в окно.
    """
    label = QLabel(text, parent)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    label.setMinimumWidth(140)
    return label


class Card(QFrame):
    """Панель с заголовком и вертикальной раскладкой внутри."""

    def __init__(self, title: str = "", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(12)
        if title:
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            self._layout.addWidget(label)
        if hint:
            self._layout.addWidget(hint_label(hint, self))

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def set_hot(self, hot: bool) -> None:
        self.setObjectName("CardHot" if hot else "Card")
        self.style().unpolish(self)
        self.style().polish(self)


class ToggleSwitch(QCheckBox):
    """Анимированный переключатель вместо стандартной галочки."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(50, 26)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, get_knob, set_knob)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 3, self.width() - 2, self.height() - 6)

        track = QLinearGradient(rect.topLeft(), rect.topRight())
        if self._pos > 0.01:
            track.setColorAt(0, QColor(theme.ACCENT_2))
            track.setColorAt(1, QColor(theme.ACCENT))
        else:
            track.setColorAt(0, QColor(theme.BG))
            track.setColorAt(1, QColor(theme.BG))
        painter.setBrush(QBrush(track))
        painter.setPen(QPen(QColor(theme.ACCENT if self._pos > 0.5 else theme.BORDER), 1))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        travel = rect.width() - rect.height() + 2
        x = rect.left() + 1 + travel * self._pos
        knob = QRectF(x, rect.top() + 1, rect.height() - 2, rect.height() - 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF") if self._pos > 0.5 else QColor(theme.TEXT_MUTED))
        painter.drawEllipse(knob)
        painter.end()


class LevelMeter(QWidget):
    """Полоса уровня микрофона с неоновым градиентом и плавным спадом."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setMinimumWidth(120)
        self._level = 0.0
        self._peak = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(40)

    def set_level(self, value: float) -> None:
        self._level = max(0.0, min(1.0, value))
        self._peak = max(self._peak, self._level)
        self.update()

    def _decay(self) -> None:
        if self._level > 0.001 or self._peak > 0.001:
            self._level *= 0.82
            self._peak *= 0.95
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.BG))
        painter.drawRoundedRect(rect, 5, 5)

        if self._level > 0.005:
            fill = QRectF(0, 0, rect.width() * self._level, rect.height())
            grad = QLinearGradient(rect.topLeft(), rect.topRight())
            grad.setColorAt(0.0, QColor(theme.ACCENT_2))
            grad.setColorAt(0.6, QColor(theme.ACCENT))
            grad.setColorAt(1.0, QColor(theme.DANGER))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(fill, 5, 5)

        if self._peak > 0.02:
            x = rect.width() * self._peak
            painter.setPen(QPen(QColor(theme.TEXT), 1))
            painter.drawLine(x, 1, x, rect.height() - 1)
        painter.end()


class StatusOrb(QWidget):
    """Большой круг состояния: пульсирует, когда идёт заглушение.

    Размер подстраивается под доступное место, поэтому при узком окне круг
    уменьшается, а не наползает на соседние виджеты.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(92, 92)
        self.setMaximumHeight(148)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._phase = 0.0
        self._muted = False
        self._active = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_state(self, active: bool, muted: bool) -> None:
        self._active = active
        self._muted = muted
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.045) % 6.2832
        if self._active:
            self.update()

    def paintEvent(self, event) -> None:
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        # Всё строится от доступного места, с запасом под свечение.
        unit = min(self.width(), self.height()) / 2
        r = unit * 0.60
        pulse = (math.sin(self._phase) + 1) / 2

        if self._muted:
            base, edge = QColor(theme.DANGER), QColor("#FF8AAE")
        elif self._active:
            base, edge = QColor(theme.ACCENT), QColor("#D78BFF")
        else:
            base, edge = QColor(theme.BORDER), QColor(theme.TEXT_MUTED)

        if self._active or self._muted:
            radius = r * 1.18 + unit * 0.22 * pulse
            halo = QRadialGradient(cx, cy, radius)
            color = QColor(base)
            color.setAlpha(int(70 + pulse * 60))
            halo.setColorAt(0.55, color)
            halo.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(halo))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        ring = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
        ring.setColorAt(0, base)
        ring.setColorAt(1, edge)
        painter.setPen(QPen(QBrush(ring), max(2.0, r * 0.09)))
        painter.setBrush(QColor(theme.CARD))
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # микрофон внутри круга, тоже в долях радиуса
        stroke = max(2.0, r * 0.07)
        painter.setPen(QPen(base, stroke, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            QRectF(cx - r * 0.18, cy - r * 0.45, r * 0.36, r * 0.60),
            r * 0.18, r * 0.18,
        )
        painter.drawArc(
            QRectF(cx - r * 0.34, cy - r * 0.27, r * 0.68, r * 0.68), 180 * 16, 180 * 16
        )
        painter.drawLine(cx, cy + r * 0.41, cx, cy + r * 0.55)
        if self._muted:
            painter.setPen(QPen(QColor(theme.DANGER), stroke * 1.3, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(cx - r * 0.5, cy + r * 0.5, cx + r * 0.5, cy - r * 0.5)
        painter.end()


class FlowLayout(QLayout):
    """Раскладка с переносом: элементы, не влезшие в строку, уходят на следующую.

    Нужна для рядов бейджей — при узком окне они переносятся, а не вылезают
    за край карточки.
    """

    def __init__(self, parent=None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    def _layout(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        right = rect.right() - margins.right()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > right and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


class Row(QWidget):
    """Строка настройки: подпись слева, управляющий элемент справа."""

    def __init__(self, label: str, control: QWidget, hint: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)

        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        text = QLabel(label)
        text.setWordWrap(True)
        text.setMinimumWidth(120)
        line.addWidget(text, 1)
        line.addStretch(1)
        line.addWidget(control)
        outer.addLayout(line)

        if hint:
            outer.addWidget(hint_label(hint, self))
        self.control = control


class SliderRow(QWidget):
    """Ползунок с живой подписью значения.

    Если задан hard_min/hard_max, вместо подписи появляется поле ввода: ползунок
    остаётся для удобных значений, а вписать можно куда больше — например,
    поднять усиление далеко за пределы шкалы.
    """

    changed = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, value: int,
                 suffix: str = "", hint: str = "", step: int = 1,
                 hard_min: int | None = None, hard_max: int | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.suffix = suffix
        self.editable = hard_min is not None and hard_max is not None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        caption = QLabel(label)
        caption.setWordWrap(True)
        caption.setMinimumWidth(110)
        head.addWidget(caption, 1)

        if self.editable:
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(0)
            self.spin.setRange(float(hard_min), float(hard_max))
            self.spin.setSingleStep(1.0)
            self.spin.setSuffix(suffix)
            self.spin.setValue(float(value))
            # Не фиксируем ширину: в узкой карточке поле должно сжиматься,
            # иначе оно вылезает за её край.
            self.spin.setMinimumWidth(72)
            self.spin.setMaximumWidth(100)
            self.spin.setAlignment(Qt.AlignRight)
            self.spin.setToolTip(
                f"Можно вписать значение вручную: от {hard_min} до {hard_max}"
            )
            self.spin.valueChanged.connect(self._on_spin)
            head.addWidget(self.spin)
            self.value_label = None
        else:
            self.spin = None
            self.value_label = QLabel(f"{value}{suffix}")
            self.value_label.setObjectName("Value")
            head.addWidget(self.value_label)
        outer.addLayout(head)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setSingleStep(step)
        self.slider.setPageStep(step * 5)
        self.slider.setValue(max(minimum, min(maximum, value)))
        self.slider.valueChanged.connect(self._on_slider)
        outer.addWidget(self.slider)

        if hint:
            outer.addWidget(hint_label(hint, self))

    # ---------------------------------------------------------- изменения
    def _on_slider(self, value: int) -> None:
        if self.spin is not None:
            self.spin.blockSignals(True)
            self.spin.setValue(float(value))
            self.spin.blockSignals(False)
        else:
            self.value_label.setText(f"{value}{self.suffix}")
        self.changed.emit(value)

    def _on_spin(self, value: float) -> None:
        number = int(round(value))
        self.slider.blockSignals(True)
        self.slider.setValue(max(self.slider.minimum(),
                                 min(self.slider.maximum(), number)))
        self.slider.blockSignals(False)
        self.changed.emit(number)

    def value(self) -> int:
        if self.spin is not None:
            return int(round(self.spin.value()))
        return self.slider.value()

    def set_value(self, value: int, silent: bool = False) -> None:
        """silent=True — обновить элементы, не поднимая сигнал изменения.

        Нужно при смене профиля: значения расставляются программно.
        """
        if silent:
            self.slider.blockSignals(True)
            self.slider.setValue(max(self.slider.minimum(),
                                     min(self.slider.maximum(), value)))
            self.slider.blockSignals(False)
            if self.spin is not None:
                self.spin.blockSignals(True)
                self.spin.setValue(float(value))
                self.spin.blockSignals(False)
            elif self.value_label is not None:
                self.value_label.setText(f"{value}{self.suffix}")
        elif self.spin is not None:
            self.spin.setValue(float(value))
        else:
            self.slider.setValue(value)


class DeviceCombo(QComboBox):
    """Выпадающий список устройств, помнящий индексы sounddevice."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Названия устройств длинные, но растягивать ими всю страницу нельзя.
        self.setMinimumWidth(170)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

    def fill(self, devices, selected: int | None, highlight: tuple = ()) -> None:
        self.blockSignals(True)
        self.clear()
        self.addItem("— не выбрано —", None)
        for dev in devices:
            mark = " ★" if any(h in dev.name.lower() for h in highlight) else ""
            self.addItem(f"{dev.name}{mark}   ({dev.hostapi})", dev.index)
        index = self.findData(selected)
        self.setCurrentIndex(index if index >= 0 else 0)
        self.blockSignals(False)

    def selected_device(self) -> int | None:
        return self.currentData()


class Badge(QLabel):
    """Цветная пилюля состояния.

    Длинный текст обрезается многоточием и уходит в подсказку, иначе один
    бейдж растянул бы всю карточку.
    """

    MAX_WIDTH = 230

    def __init__(self, text: str = "", color: str = theme.TEXT_MUTED,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.set_color(color)
        self.setText(text)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(
            f"background: rgba(0,0,0,0.25); border: 1px solid {color};"
            f"color: {color}; border-radius: 9px; padding: 4px 11px;"
            f"font-size: 11px; font-weight: 600;"
        )

    def setText(self, text: str) -> None:
        self._full_text = text
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(text, Qt.ElideRight, self.MAX_WIDTH - 26)
        super().setText(elided)
        self.setToolTip(text if elided != text else "")

    def set_state(self, text: str, color: str) -> None:
        self.setText(text)
        self.set_color(color)
