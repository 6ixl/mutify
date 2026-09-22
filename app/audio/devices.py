# -*- coding: utf-8 -*-
"""Перечисление звуковых устройств и поиск виртуального кабеля."""
from __future__ import annotations

from dataclasses import dataclass

VB_HINTS = ("cable input", "vb-audio", "vb-cable", "voicemeeter", "virtual cable")


@dataclass
class Device:
    index: int
    name: str
    channels: int
    samplerate: float
    hostapi: str

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.hostapi}"


def _hostapis() -> list[str]:
    import sounddevice as sd

    return [api["name"] for api in sd.query_hostapis()]


def _collect(kind: str) -> list[Device]:
    import sounddevice as sd

    apis = _hostapis()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    out: list[Device] = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev[key] < 1:
            continue
        out.append(
            Device(
                index=idx,
                name=dev["name"],
                channels=dev[key],
                samplerate=dev["default_samplerate"],
                hostapi=apis[dev["hostapi"]] if dev["hostapi"] < len(apis) else "?",
            )
        )
    return out


def inputs() -> list[Device]:
    return _collect("input")


def outputs() -> list[Device]:
    return _collect("output")


def default_input() -> int | None:
    import sounddevice as sd

    try:
        value = sd.default.device[0]
        return int(value) if value is not None and value >= 0 else None
    except Exception:
        return None


def find_virtual_cable() -> Device | None:
    """Ищет VB-Cable среди устройств вывода — туда уходит очищенный звук."""
    for dev in outputs():
        low = dev.name.lower()
        if any(hint in low for hint in VB_HINTS):
            return dev
    return None


def describe(index: int | None, kind: str) -> str:
    if index is None:
        return "не выбрано"
    pool = inputs() if kind == "input" else outputs()
    for dev in pool:
        if dev.index == index:
            return dev.name
    return f"устройство #{index} (недоступно)"


def refresh_backend() -> None:
    """Перечитать список устройств.

    PortAudio кэширует устройства при первом обращении, поэтому после установки
    нового драйвера его нужно перезапустить — иначе свежий кабель не появится.
    """
    import sounddevice as sd

    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def exists(index: int | None, kind: str) -> bool:
    if index is None:
        return False
    pool = inputs() if kind == "input" else outputs()
    return any(dev.index == index for dev in pool)


def autoconfigure(cfg) -> list[str]:
    """Сам подбирает микрофон и виртуальный кабель.

    Вызывается при запуске и после установки драйвера, чтобы пользователю не
    приходилось выбирать устройства руками. Уже выбранные рабочие устройства
    не трогаем.
    """
    changed: list[str] = []

    if not exists(cfg.input_device, "input"):
        picked = default_input()
        if picked is None:
            available = inputs()
            picked = available[0].index if available else None
        if picked is not None:
            cfg.input_device = picked
            changed.append("микрофон: " + describe(picked, "input"))

    if not exists(cfg.output_device, "output"):
        cable = find_virtual_cable()
        if cable is not None:
            cfg.output_device = cable.index
            changed.append("выход: " + cable.name)

    return changed
