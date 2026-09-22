# -*- coding: utf-8 -*-
"""Иконка приложения: рисуется кодом, файлы-картинки не нужны.

Неоново-фиолетовый круг с перечёркнутым микрофоном — тот же знак, что
показывает индикатор на главной странице.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap,
    QRadialGradient
)

from app.paths import ASSETS_DIR
from app.ui import theme

ICON_PNG = ASSETS_DIR / "icon.png"
ICON_ICO = ASSETS_DIR / "icon.ico"


def draw_logo(size: int, muted: bool = True, background: bool = True) -> QPixmap:
    """Рисует знак приложения указанного размера."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0          # все размеры заданы для холста 256x256
    cx = cy = size / 2

    if background:
        # скруглённый тёмный квадрат с фиолетовым свечением внутри
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#120A22"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), 56 * s, 56 * s)

        halo = QRadialGradient(cx, cy, 120 * s)
        halo.setColorAt(0.0, QColor(177, 75, 255, 120))
        halo.setColorAt(0.65, QColor(122, 43, 255, 40))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(halo))
        painter.drawRoundedRect(QRectF(0, 0, size, size), 56 * s, 56 * s)

    # кольцо
    r = 86 * s
    ring = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
    ring.setColorAt(0.0, QColor(theme.ACCENT_2))
    ring.setColorAt(1.0, QColor("#D78BFF"))
    painter.setPen(QPen(QBrush(ring), 10 * s))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    # микрофон
    pen = QPen(QColor("#EDE6FA"), 11 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    body = QRectF(cx - 21 * s, cy - 54 * s, 42 * s, 68 * s)
    painter.drawRoundedRect(body, 21 * s, 21 * s)
    painter.drawArc(QRectF(cx - 38 * s, cy - 32 * s, 76 * s, 76 * s), 180 * 16, 180 * 16)
    painter.drawLine(cx, cy + 34 * s, cx, cy + 52 * s)

    if muted:
        # перечёркивание: тёмная подложка, чтобы линия читалась поверх микрофона
        painter.setPen(QPen(QColor("#120A22"), 24 * s, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(cx - 52 * s, cy + 56 * s, cx + 52 * s, cy - 56 * s)
        painter.setPen(QPen(QColor(theme.ACCENT), 12 * s, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(cx - 52 * s, cy + 56 * s, cx + 52 * s, cy - 56 * s)

    painter.end()
    return pixmap


def logo_with_counter(size: int, count: int, muted: bool = False) -> QPixmap:
    """Значок со счётчиком перехваченных слов в углу — для трея."""
    pixmap = draw_logo(size, muted=muted)
    if count <= 0:
        return pixmap

    text = str(count) if count < 100 else "99+"
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0

    width = (20 if len(text) < 3 else 27) * s
    height = 20 * s
    rect = QRectF(size - width - 2 * s, size - height - 2 * s, width, height)

    painter.setPen(QPen(QColor("#120A22"), 2 * s))
    painter.setBrush(QColor(theme.DANGER))
    painter.drawRoundedRect(rect, height / 2, height / 2)

    font = QFont("Segoe UI")
    font.setPixelSize(int(max(7, 13 * s)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(rect, Qt.AlignCenter, text)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """Иконка для окна и трея во всех нужных размерах."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_logo(size))
    return icon


def _png_bytes(pixmap: QPixmap) -> bytes:
    # QByteArray держим в переменной: временный объект Qt успеет освободить.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def export_files() -> tuple[Path, Path]:
    """Сохраняет icon.png и icon.ico — нужны для ярлыка и сборки .exe."""
    big = draw_logo(256)
    big.save(str(ICON_PNG), "PNG")

    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [_png_bytes(draw_logo(s)) for s in sizes]

    # ICO-контейнер: начиная с Windows Vista внутрь кладут готовые PNG.
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, payload = b"", b""
    for size, data in zip(sizes, images):
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0, 0, 1, 32, len(data), offset,
        )
        payload += data
        offset += len(data)

    ICON_ICO.write_bytes(header + entries + payload)
    return ICON_PNG, ICON_ICO
