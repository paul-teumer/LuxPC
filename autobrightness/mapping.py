"""Abbildung des Umgebungslichts auf die Bildschirmhelligkeit sowie Glättung."""

from __future__ import annotations

import math
from typing import Optional

from .config import SettingsData


def target_brightness(exposure_value: float, settings: SettingsData) -> float:
    """Lineare Abbildung in Blendenstufen: dunkel -> Minimum, hell -> Maximum, plus Versatz."""
    span = settings.bright_exposure_value - settings.dark_exposure_value
    ratio = (exposure_value - settings.dark_exposure_value) / span
    ratio = max(0.0, min(1.0, ratio))
    minimum = settings.min_brightness_percent
    maximum = settings.max_brightness_percent
    value = minimum + ratio * (maximum - minimum) + settings.brightness_offset_percent
    return max(0.0, min(100.0, value))


class ExposureValueSmoother:
    """Exponentielle Glättung mit zeitunabhängiger Zeitkonstante.

    Messwerte kommen selten; zwischen ihnen läuft der Wert kontinuierlich auf den
    letzten Messwert zu, sodass die Helligkeit weich nachgeführt wird.
    """

    def __init__(self) -> None:
        self._value: Optional[float] = None
        self._sample: Optional[float] = None

    def reset(self) -> None:
        self._value = None
        self._sample = None

    def set_sample(self, sample: float) -> None:
        self._sample = sample
        if self._value is None:
            self._value = sample

    def advance(self, elapsed_s: float, response_time_s: float) -> Optional[float]:
        if self._sample is None:
            return None
        if response_time_s <= 0:
            self._value = self._sample
        else:
            weight = 1.0 - math.exp(-elapsed_s / response_time_s)
            self._value += weight * (self._sample - self._value)
        return self._value


def should_apply(candidate: int, last_applied: Optional[int], hysteresis_percent: int) -> bool:
    """Neue Helligkeit nur bei ausreichender Abweichung; Randwerte werden immer erreicht."""
    if last_applied is None:
        return True
    if candidate == last_applied:
        return False
    if candidate in (0, 100):
        return True
    return abs(candidate - last_applied) >= hysteresis_percent
