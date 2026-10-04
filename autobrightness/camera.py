"""Webcam als Belichtungsmesser: regelt die Belichtungszeit und liefert den Umgebungslichtwert.

Die Kamera wird nur für die Dauer einer Messung gehalten: Solange ein
DirectShow-Zugriff besteht, erhalten andere Programme (Media Foundation:
Teams, Zoom, Browser) kein Bild.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2

from . import metering
from .dshow import CameraExposureControl

SETTLE_FRAMES = 4
WARMUP_FRAMES = 8
SETTLE_SECONDS = 0.15
MAX_ADJUSTMENTS = 5
AVERAGED_FRAMES = 5
FALLBACK_EXPOSURE_LOG2_SECONDS = -6


class CameraError(RuntimeError):
    pass


class CameraInUseError(CameraError):
    """Ein anderes Programm hat die Kamera während der Messung geöffnet."""


@dataclass(frozen=True)
class Reading:
    exposure_value: float
    exposure_log2_seconds: int
    mean_level: float
    reliable: bool
    exposure_control_available: bool


class ExposureMeterCamera:
    """Merkt sich die zuletzt passende Belichtung, damit jede Messung nahe am Ziel startet."""

    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self._capture: Optional[cv2.VideoCapture] = None
        self._control: Optional[CameraExposureControl] = None
        self._minimum = self._maximum = FALLBACK_EXPOSURE_LOG2_SECONDS
        self._exposure: Optional[int] = None

    def open(self) -> None:
        capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            raise CameraError("Kamera belegt oder nicht verfügbar")
        self._capture = capture
        try:
            self._control = CameraExposureControl(self.camera_index)
            self._minimum, self._maximum, _, default = self._control.exposure_range()
            if self._minimum >= self._maximum:
                raise CameraError("Belichtung nicht einstellbar")
            start = default if self._exposure is None else self._exposure
            self._exposure = max(self._minimum, min(self._maximum, start))
            self._control.set_manual(self._exposure)
        except Exception:
            self._discard_control()
        self._grab_gray(WARMUP_FRAMES)

    @property
    def exposure_control_available(self) -> bool:
        return self._control is not None

    def _discard_control(self) -> None:
        if self._control is not None:
            self._control.close()
        self._control = None
        self._minimum = self._maximum = FALLBACK_EXPOSURE_LOG2_SECONDS
        self._exposure = FALLBACK_EXPOSURE_LOG2_SECONDS

    def _grab_gray(self, frames_to_discard: int):
        assert self._capture is not None
        for _ in range(frames_to_discard):
            self._capture.grab()
            time.sleep(0.01)
        ok, frame = self._capture.read()
        if not ok:
            raise CameraError("Kein Bild von der Kamera")
        small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    def measure(self, is_camera_free: Callable[[], bool] = lambda: True) -> Reading:
        """Regelt die Belichtung ein und liefert den Median mehrerer Einzelbilder.

        Vor jedem Schritt wird geprüft, ob die Kamera noch uns allein gehört; sonst
        bricht die Messung sofort ab, damit die Belichtung des anderen Programms
        nicht durch unsere Einstellung gestört wird.
        """
        if self._capture is None or self._exposure is None:
            raise CameraError("Kamera nicht geöffnet")

        def ensure_camera_free() -> None:
            if not is_camera_free():
                raise CameraInUseError("Kamera von anderem Programm belegt")

        ensure_camera_free()
        frame_statistics = metering.frame_statistics(self._grab_gray(SETTLE_FRAMES))
        for _ in range(MAX_ADJUSTMENTS):
            ensure_camera_free()
            wanted = metering.next_exposure(
                frame_statistics, self._exposure, self._minimum, self._maximum
            )
            if wanted == self._exposure or self._control is None:
                break
            self._control.set_manual(wanted)
            self._exposure = wanted
            time.sleep(SETTLE_SECONDS)
            frame_statistics = metering.frame_statistics(self._grab_gray(SETTLE_FRAMES))

        samples = [frame_statistics]
        for _ in range(AVERAGED_FRAMES - 1):
            ensure_camera_free()
            samples.append(metering.frame_statistics(self._grab_gray(1)))
        exposure_values = [
            metering.exposure_value(sample.linear_level, self._exposure) for sample in samples
        ]
        return Reading(
            exposure_value=statistics.median(exposure_values),
            exposure_log2_seconds=self._exposure,
            mean_level=statistics.median(sample.mean_level for sample in samples),
            reliable=metering.reading_is_reliable(
                frame_statistics, self._exposure, self._minimum, self._maximum
            ),
            exposure_control_available=self._control is not None,
        )

    def close(self) -> None:
        """Gibt die Kamera frei und stellt die Belichtungsautomatik wieder her."""
        if self._control is not None:
            try:
                self._control.set_auto()
            except Exception:
                pass
            self._control.close()
            self._control = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
