# -*- coding: utf-8 -*-
"""Неоново-фиолетовая тема. Вся палитра собрана здесь."""
from __future__ import annotations

BG_DEEP = "#070310"
BG = "#0D0718"
CARD = "#150C26"
CARD_HOVER = "#1C1033"
BORDER = "#2E1A52"
BORDER_HOT = "#7A2BFF"
TEXT = "#EDE6FA"
TEXT_DIM = "#9A8CB8"
TEXT_MUTED = "#6E6188"
ACCENT = "#B14BFF"
ACCENT_2 = "#7A2BFF"
ACCENT_SOFT = "#3B1D6B"
DANGER = "#FF4B7D"
OK = "#37E6A8"
WARN = "#FFB84B"


# Готовые неоновые пары «акцент — тёмный акцент» для смены цвета интерфейса.
PRESETS: dict[str, tuple[str, str]] = {
    "Фиолетовый": ("#B14BFF", "#7A2BFF"),
    "Розовый": ("#FF4BD8", "#B02BFF"),
    "Голубой": ("#4BC8FF", "#2B6BFF"),
    "Мятный": ("#37E6A8", "#12A375"),
    "Янтарный": ("#FFB84B", "#FF7A2B"),
    "Алый": ("#FF4B6E", "#C4204A"),
}


def preset_name(accent: str) -> str:
    for name, (first, _) in PRESETS.items():
        if first.lower() == (accent or "").lower():
            return name
    return "Свой"


def stylesheet(accent: str = ACCENT, accent_2: str = ACCENT_2) -> str:
    return f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}

QWidget#Root {{
    background: {BG_DEEP};
}}

QWidget#Sidebar {{
    background: {BG};
    border-right: 1px solid {BORDER};
}}

QLabel#Logo {{
    font-size: 22px;
    font-weight: 800;
    color: {accent};
    letter-spacing: 3px;
    padding: 22px 18px 4px 18px;
}}

QLabel#LogoSub {{
    font-size: 10px;
    color: {TEXT_MUTED};
    letter-spacing: 2px;
    padding: 0 18px 18px 20px;
}}

QPushButton#NavItem {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    padding: 13px 18px;
    text-align: left;
    font-size: 13px;
    color: {TEXT_DIM};
}}
QPushButton#NavItem:hover {{
    background: {CARD};
    color: {TEXT};
}}
QPushButton#NavItem:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_SOFT}, stop:1 transparent);
    border-left: 3px solid {accent};
    color: {TEXT};
    font-weight: 600;
}}

QWidget#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QWidget#CardHot {{
    background: {CARD};
    border: 1px solid {accent};
    border-radius: 14px;
}}

QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageHint {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {accent};
    letter-spacing: 1px;
}}
QLabel#Hint {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}
QLabel#Value {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#BigStat {{
    font-size: 30px;
    font-weight: 800;
    color: {accent};
}}
QLabel#Transcript {{
    font-size: 15px;
    color: {TEXT};
    padding: 10px;
}}

QPushButton {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 9px 16px;
    color: {TEXT};
}}
QPushButton:hover {{
    border-color: {accent};
    background: {ACCENT_SOFT};
}}
QPushButton:pressed {{
    background: {accent_2};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border-color: {BORDER};
    background: {CARD};
}}

QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_2}, stop:1 {accent});
    border: none;
    border-radius: 11px;
    padding: 13px 14px;
    font-size: 14px;
    font-weight: 700;
    color: #FFFFFF;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 #D07BFF);
}}
QPushButton#Danger {{
    background: transparent;
    border: 1px solid {DANGER};
    color: {DANGER};
    border-radius: 11px;
    padding: 13px 14px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton#Danger:hover {{
    background: rgba(255, 75, 125, 0.15);
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    padding: 7px 12px;
    font-size: 12px;
}}
QPushButton#Ghost:hover {{
    border-color: {accent};
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 9px 12px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {accent};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {accent};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    padding: 4px;
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: {BG};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent_2}, stop:1 {accent});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    border: 2px solid {BG};
}}
QSlider::handle:horizontal:hover {{
    background: #D78BFF;
}}

QListWidget {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 5px;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 7px;
}}
QListWidget::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QListWidget::item:hover {{
    background: {CARD_HOVER};
}}

QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid {BORDER};
    background: {BG};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {accent};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}

QToolTip {{
    background: {CARD};
    border: 1px solid {accent};
    border-radius: 6px;
    padding: 6px;
    color: {TEXT};
}}
"""
