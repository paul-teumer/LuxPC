"""Belichtungsmessung: aus Bild und Belichtungszeit wird der Umgebungslichtwert.

Die Kamera hat feste Blende und (hier) festen Gain. Die Szenenhelligkeit
folgt daher aus dem linearisierten Bildmittelwert geteilt durch die
Belichtungszeit. Der Belichtungswert wird in Blendenstufen (log2) geführt:

    exposure_value = log2(lineare_Bildhelligkeit) - log2(Belichtungszeit_s)

Eine Verdopplung des Umgebungslichts erhöht ihn um genau 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

CAMERA_GAMMA = 2.2
LOWER_VALID_LEVEL = 0.02
UPPER_VALID_LEVEL = 0.97
TARGET_LEVEL = 0.45
UNDEREXPOSED_BELOW = 0.12
OVEREXPOSED_ABOVE = 0.85
MAX_CLIPPED_FRACTION = 0.10
MAX_STEP = 4


@dataclass(frozen=True)
class FrameStatistics:
    mean_level: float
    linear_level: float
    clipped_fraction: float


def frame_statistics(gray_frame: np.ndarray) -> FrameStatistics:
    """Kennzahlen eines 8-Bit-Graubilds; Über-/Unterbelichtete Pixel zählen nicht in den Mittelwert."""
    levels = gray_frame.astype(np.float32) / 255.0
    clipped = float(np.mean(levels >= UPPER_VALID_LEVEL))
    valid = levels[(levels > LOWER_VALID_LEVEL) & (levels < UPPER_VALID_LEVEL)]
    if valid.size == 0:
        mean_level = float(levels.mean())
    else:
        mean_level = float(valid.mean())
    linear_level = max(mean_level, 1e-4) ** CAMERA_GAMMA
    return FrameStatistics(mean_level, linear_level, clipped)


def exposure_value(linear_level: float, exposure_log2_seconds: int) -> float:
    return math.log2(linear_level) - exposure_log2_seconds


def next_exposure(
    statistics: FrameStatistics, exposure_log2_seconds: int, minimum: int, maximum: int
) -> int:
    """Zielbelichtung, damit das Bild im auswertbaren Mittelfeld liegt (sonst unverändert)."""
    overexposed = (
        statistics.mean_level > OVEREXPOSED_ABOVE
        or statistics.clipped_fraction > MAX_CLIPPED_FRACTION
    )
    underexposed = statistics.mean_level < UNDEREXPOSED_BELOW
    if not (overexposed or underexposed):
        return exposure_log2_seconds
    wanted = math.log2(TARGET_LEVEL**CAMERA_GAMMA / statistics.linear_level)
    step = int(round(max(-MAX_STEP, min(MAX_STEP, wanted))))
    if overexposed:
        step = min(step, -1)
    else:
        step = max(step, 1)
    return max(minimum, min(maximum, exposure_log2_seconds + step))


def reading_is_reliable(
    statistics: FrameStatistics, exposure_log2_seconds: int, minimum: int, maximum: int
) -> bool:
    """Am Belichtungslimit ist ein Messwert nur Grenzwert, aber nie ungültig überbelichtet."""
    if statistics.mean_level > OVEREXPOSED_ABOVE and exposure_log2_seconds > minimum:
        return False
    if statistics.mean_level < UNDEREXPOSED_BELOW and exposure_log2_seconds < maximum:
        return False
    return True
