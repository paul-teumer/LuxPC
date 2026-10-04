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


class BrightnessRamp:
    """Führt die gesetzte Helligkeit in kleinen Schritten nach.

    Ein Schritt beträgt mindestens einen Prozentpunkt und höchstens ein Viertel des Abstands
    zum Ziel: kleine Abweichungen laufen fein, große Sprünge werden schnell, aber weich überbrückt.

    Eine Bewegung beginnt erst, wenn der Zielwert mindestens um die Mindeständerung
    abweicht (gegen Flackern), und läuft dann Schritt für Schritt bis zum Ziel.
    """

    def __init__(self, applied: Optional[int] = None) -> None:
        self.applied = applied
        self.moving = False

    def next_value(self, level: float, hysteresis_percent: int) -> Optional[int]:
        target = round(level)
        if self.applied is None:
            return target
        difference = target - self.applied
        if difference == 0:
            self.moving = False
            return None
        if not self.moving and abs(difference) < hysteresis_percent and target not in (0, 100):
            return None
        self.moving = True
        step = max(1, math.ceil(abs(difference) / 4))
        return self.applied + (step if difference > 0 else -step)
