"""Hintergrunddienst: misst das Umgebungslicht und regelt die Bildschirmhelligkeit."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, Optional

from . import camera_usage, display, mapping
from .camera import CameraError, CameraInUseError, ExposureMeterCamera
from .config import Settings

TICK_S = 1.0
RAMP_TICK_S = 0.1
RETRY_DELAY_S = 5.0
HISTORY_LENGTH = 240


@dataclass(frozen=True)
class Status:
    state: str = "starting"  # starting | running | disabled | busy | error
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
        get_brightness: Callable[[Optional[str]], Optional[int]] = display.get_brightness,
        apply_night_light: Callable[[int], bool] = display.apply_night_light,
        find_camera_users: Callable[[], list[str]] = camera_usage.applications_using_camera,
    ) -> None:
        self._settings = settings
        self._camera_factory = camera_factory
        self._set_brightness = set_brightness
        self._get_brightness = get_brightness
        self._apply_night_light = apply_night_light
        self._find_camera_users = find_camera_users
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
        """Übernimmt die letzte Messung als dunklen bzw. hellen Referenzpunkt."""
        current = self.status.raw_exposure_value
        if current is None:
            return False
        key = "dark_exposure_value" if dark else "bright_exposure_value"
        self._settings.update(**{key: round(current, 2)})
        return True

    def _camera_is_free(self) -> bool:
        users = self._find_camera_users()
        if users:
            self._publish(state="busy", message=", ".join(users))
        return not users

    def _measure(self, camera: ExposureMeterCamera):
        """Eine Messung mit sofortiger Freigabe der Kamera; None, wenn sie nicht möglich ist."""
        if not self._camera_is_free():
            return None
        try:
            camera.open()
            return camera.measure(self._camera_is_free)
        except CameraInUseError:
            return None
        except CameraError:
            self._publish(state="busy", message="")
            return None
        except Exception as error:
            self._publish(state="error", message=str(error))
            return None
        finally:
            camera.close()

    def _run(self) -> None:
        camera: Optional[ExposureMeterCamera] = None
        camera_index: Optional[int] = None
        smoother = mapping.ExposureValueSmoother()
        ramp = mapping.BrightnessRamp()
        last_history = 0.0
        last_night_light: Optional[int] = None
        next_measurement = 0.0
        last_tick = time.monotonic()
        try:
            while not self._stop.is_set():
                settings = self._settings.snapshot()
                if settings.night_shift_percent != last_night_light:
                    self._apply_night_light(settings.night_shift_percent)
                    last_night_light = settings.night_shift_percent

                now = time.monotonic()
                elapsed, last_tick = now - last_tick, now
                if not settings.enabled:
                    smoother.reset()
                    ramp = mapping.BrightnessRamp()
                    next_measurement = 0.0
                    self._publish(state="disabled", message="Automatik pausiert")
                    self._wait(TICK_S)
                    continue

                if now >= next_measurement:
                    if camera is None or camera_index != settings.camera_index:
                        camera = self._camera_factory(settings.camera_index)
                        camera_index = settings.camera_index
                    reading = self._measure(camera)
                    if reading is None:
                        next_measurement = time.monotonic() + RETRY_DELAY_S
                    else:
                        next_measurement = time.monotonic() + settings.measure_interval_s
                        smoother.set_sample(reading.exposure_value)
                        self._publish(
                            state="running",
                            message="",
                            raw_exposure_value=reading.exposure_value,
                            exposure_log2_seconds=reading.exposure_log2_seconds,
                            reliable=reading.reliable,
                            exposure_control_available=reading.exposure_control_available,
                        )
                    last_tick = time.monotonic()

                wait_s = TICK_S
                smoothed = smoother.advance(elapsed, settings.response_time_s)
                if smoothed is not None:
                    level = mapping.target_brightness(smoothed, settings)
                    if ramp.applied is None:
                        ramp.applied = self._get_brightness(settings.monitor)
                    step = ramp.next_value(level, settings.hysteresis_percent)
                    if step is not None:
                        try:
                            self._set_brightness(step, settings.monitor)
                            ramp.applied = step
                            if self.status.state == "error":
                                self._publish(state="running", message="")
                        except Exception as error:
                            self._publish(state="error", message=f"Helligkeit nicht setzbar: {error}")
                    if ramp.moving:
                        wait_s = RAMP_TICK_S
                    if now - last_history >= TICK_S:
                        last_history = now
                        self.history.append((time.time(), smoothed, round(level)))
                    self._publish(exposure_value=smoothed, target_percent=round(level), applied_percent=ramp.applied)
                self._wait(wait_s)
        finally:
            if camera is not None:
                camera.close()

    def _wait(self, seconds: float) -> None:
        self._wake.wait(seconds)
        self._wake.clear()
