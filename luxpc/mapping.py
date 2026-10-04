"""Abbildung des Umgebungslichts auf die Bildschirmhelligkeit sowie Glättung."""

from __future__ import annotations

import math
from typing import Optional

from .config import SettingsData


def curve_brightness(exposure_value: float, points: list[list[float]]) -> float:
    """Stückweise lineare Kurve durch die (nach Blendenstufe sortierten) Kalibrierpunkte; außerhalb konstant."""
    if exposure_value <= points[0][0]:
        return points[0][1]
    for (left_ev, left_percent), (right_ev, right_percent) in zip(points, points[1:]):
        if exposure_value <= right_ev:
            ratio = (exposure_value - left_ev) / (right_ev - left_ev)
            return left_percent + ratio * (right_percent - left_percent)
    return points[-1][1]


def target_brightness(exposure_value: float, settings: SettingsData) -> float:
    """Kalibrierkurve plus Versatz, begrenzt auf Minimum und Maximum."""
    value = curve_brightness(exposure_value, settings.calibration_points) + settings.brightness_offset_percent
    return max(float(settings.min_brightness_percent), min(float(settings.max_brightness_percent), value))


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
