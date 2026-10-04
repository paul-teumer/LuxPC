"""Hintergrunddienst: misst das Umgebungslicht und regelt die Bildschirmhelligkeit."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, Optional

from . import display, mapping
from .camera import CameraError, ExposureMeterCamera
from .config import Settings

RETRY_DELAY_S = 3.0
HISTORY_LENGTH = 240


@dataclass(frozen=True)
class Status:
    state: str = "starting"  # starting | running | disabled | error
    message: str = ""
    exposure_value: Optional[float] = None
    raw_exposure_value: Optional[float] = None
    exposure_log2_seconds: Optional[int] = None
    target_percent: Optional[int] = None
    applied_percent: Optional[int] = None
    reliable: bool = True
    exposure_control_available: bool = True


class BrightnessService:
    def __init__(
        self,
        settings: Settings,
        camera_factory: Callable[[int], ExposureMeterCamera] = ExposureMeterCamera,
        set_brightness: Callable[[int, Optional[str]], None] = display.set_brightness,
        apply_night_light: Callable[[int], bool] = display.apply_night_light,
    ) -> None:
        self._settings = settings
        self._camera_factory = camera_factory
        self._set_brightness = set_brightness
        self._apply_night_light = apply_night_light
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._status = Status()
        self.history: deque[tuple[float, float, int]] = deque(maxlen=HISTORY_LENGTH)
        settings.subscribe(self._wake.set)

    @property
    def status(self) -> Status:
        with self._lock:
            return self._status

    def _publish(self, **changes) -> None:
        with self._lock:
            self._status = replace(self._status, **changes)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="brightness-service", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._apply_night_light(0)

    def calibrate(self, dark: bool) -> bool:
        """Übernimmt das aktuelle Umgebungslicht als dunklen bzw. hellen Referenzpunkt."""
        current = self.status.exposure_value
        if current is None:
            return False
        key = "dark_exposure_value" if dark else "bright_exposure_value"
        self._settings.update(**{key: round(current, 2)})
        return True

    def _run(self) -> None:
        camera: Optional[ExposureMeterCamera] = None
        camera_index: Optional[int] = None
        smoother = mapping.ExposureValueSmoother()
        last_applied: Optional[int] = None
        last_night_light: Optional[int] = None
        last_time = time.monotonic()
        try:
            while not self._stop.is_set():
                settings = self._settings.snapshot()
                if settings.night_shift_percent != last_night_light:
                    self._apply_night_light(settings.night_shift_percent)
                    last_night_light = settings.night_shift_percent

                if camera is not None and (
                    not settings.enabled or camera_index != settings.camera_index
                ):
                    camera.close()
                    camera = None
                    smoother.reset()
                if not settings.enabled:
                    self._publish(state="disabled", message="Automatik pausiert")
                    self._wait(1.0)
                    continue

                if camera is None:
                    try:
                        camera = self._camera_factory(settings.camera_index)
                        camera.open()
                        camera_index = settings.camera_index
                        last_time = time.monotonic()
                    except Exception as error:
                        if camera is not None:
                            camera.close()
                        camera = None
                        self._publish(state="error", message=str(error))
                        self._wait(RETRY_DELAY_S)
                        continue

                try:
                    reading = camera.measure()
                except CameraError as error:
                    camera.close()
                    camera = None
                    self._publish(state="error", message=str(error))
                    self._wait(RETRY_DELAY_S)
                    continue

                now = time.monotonic()
                smoothed = smoother.update(
                    reading.exposure_value, now - last_time, settings.response_time_s
                )
                last_time = now
                target = round(mapping.target_brightness(smoothed, settings))
                if mapping.should_apply(target, last_applied, settings.hysteresis_percent):
                    try:
                        self._set_brightness(target, settings.monitor)
                        last_applied = target
                    except Exception as error:
                        self._publish(state="error", message=f"Helligkeit nicht setzbar: {error}")
                        self._wait(RETRY_DELAY_S)
                        continue
                self.history.append((time.time(), smoothed, target))
                self._publish(
                    state="running",
                    message="",
                    exposure_value=smoothed,
                    raw_exposure_value=reading.exposure_value,
                    exposure_log2_seconds=reading.exposure_log2_seconds,
                    target_percent=target,
                    applied_percent=last_applied,
                    reliable=reading.reliable,
                    exposure_control_available=reading.exposure_control_available,
                )
                self._wait(settings.measure_interval_s)
        finally:
            if camera is not None:
                camera.close()

    def _wait(self, seconds: float) -> None:
        self._wake.wait(seconds)
        self._wake.clear()
