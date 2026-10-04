"""Ansteuerung der Bildschirme: Helligkeit (DDC/CI bzw. WMI) und Nachtlicht."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

import screen_brightness_control

NIGHT_LIGHT_BLUE_REDUCTION = 0.50
NIGHT_LIGHT_GREEN_REDUCTION = 0.22


def list_monitors() -> list[str]:
    try:
        return list(screen_brightness_control.list_monitors())
    except Exception:
        return []


def set_brightness(percent: int, monitor: Optional[str]) -> None:
    percent = max(0, min(100, int(percent)))
    if monitor:
        try:
            screen_brightness_control.set_brightness(percent, display=monitor)
            return
        except Exception:
            pass
    screen_brightness_control.set_brightness(percent)


def build_gamma_ramp(percent: int):
    strength = max(0, min(100, int(percent))) / 100.0
    channel_scales = (
        1.0,
        1.0 - NIGHT_LIGHT_GREEN_REDUCTION * strength,
        1.0 - NIGHT_LIGHT_BLUE_REDUCTION * strength,
    )
    ramp = (ctypes.c_ushort * (3 * 256))()
    for channel, scale in enumerate(channel_scales):
        for level in range(256):
            ramp[channel * 256 + level] = min(65535, int(level * 256 * scale))
    return ramp


def apply_night_light(percent: int) -> bool:
    """Wärmerer Farbton über die Gamma-Rampe; 0 stellt den Normalzustand wieder her."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
    device_context = user32.GetDC(None)
    try:
        return bool(gdi32.SetDeviceGammaRamp(device_context, build_gamma_ramp(percent)))
    finally:
        user32.ReleaseDC(None, device_context)
