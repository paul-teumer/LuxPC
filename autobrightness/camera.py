"""Webcam als Belichtungsmesser: regelt die Belichtungszeit und liefert den Umgebungslichtwert."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import cv2

from . import metering
from .dshow import CameraExposureControl

SETTLE_FRAMES = 4
WARMUP_FRAMES = 15
SETTLE_SECONDS = 0.15
MAX_ADJUSTMENTS = 5
FALLBACK_EXPOSURE_LOG2_SECONDS = -6


class CameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reading:
    exposure_value: float
    exposure_log2_seconds: int
    mean_level: float
    reliable: bool
    exposure_control_available: bool


class ExposureMeterCamera:
    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self._capture: Optional[cv2.VideoCapture] = None
        self._control: Optional[CameraExposureControl] = None
        self._minimum = self._maximum = FALLBACK_EXPOSURE_LOG2_SECONDS
        self._exposure = FALLBACK_EXPOSURE_LOG2_SECONDS

    def open(self) -> None:
        capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            raise CameraError("Kamera nicht verfügbar")
        self._capture = capture
        try:
            self._control = CameraExposureControl(self.camera_index)
            self._minimum, self._maximum, _, default = self._control.exposure_range()
            if self._minimum >= self._maximum:
                raise CameraError("Belichtung nicht einstellbar")
            self._exposure = default
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
        self._minimum = self._maximum = self._exposure = FALLBACK_EXPOSURE_LOG2_SECONDS

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

    def measure(self) -> Reading:
        if self._capture is None:
            raise CameraError("Kamera nicht geöffnet")
        frames_to_discard = SETTLE_FRAMES
        statistics = metering.frame_statistics(self._grab_gray(frames_to_discard))
        for _ in range(MAX_ADJUSTMENTS):
            wanted = metering.next_exposure(
                statistics, self._exposure, self._minimum, self._maximum
            )
            if wanted == self._exposure or self._control is None:
                break
            self._control.set_manual(wanted)
            self._exposure = wanted
            time.sleep(SETTLE_SECONDS)
            statistics = metering.frame_statistics(self._grab_gray(SETTLE_FRAMES))
        return Reading(
            exposure_value=metering.exposure_value(statistics.linear_level, self._exposure),
            exposure_log2_seconds=self._exposure,
            mean_level=statistics.mean_level,
            reliable=metering.reading_is_reliable(
                statistics, self._exposure, self._minimum, self._maximum
            ),
            exposure_control_available=self._control is not None,
        )

    def close(self) -> None:
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
