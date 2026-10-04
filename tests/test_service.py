import time

from autobrightness.camera import CameraError, Reading
from autobrightness.config import Settings
from autobrightness.service import BrightnessService


class FakeCamera:
    instances: list["FakeCamera"] = []

    def __init__(self, camera_index: int, exposure_values=(10.0,), fail_open: bool = False) -> None:
        self.exposure_values = list(exposure_values)
        self.fail_open = fail_open
        self.opened = self.closed = False
        FakeCamera.instances.append(self)

    def open(self) -> None:
        if self.fail_open:
            raise CameraError("Kamera nicht verfügbar")
        self.opened = True

    def measure(self) -> Reading:
        value = self.exposure_values[0] if len(self.exposure_values) == 1 else self.exposure_values.pop(0)
        return Reading(value, -8, 0.5, True, True)

    def close(self) -> None:
        self.closed = True


def wait_for(condition, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def make_service(tmp_path, camera_factory, **settings_changes):
    settings = Settings(tmp_path / "settings.json")
    settings.update(
        measure_interval_s=0.3, response_time_s=0.0, dark_exposure_value=0.0,
        bright_exposure_value=10.0, min_brightness_percent=0, max_brightness_percent=100,
        **settings_changes,
    )
    applied, night_light = [], []
    service = BrightnessService(
        settings, camera_factory,
        set_brightness=lambda percent, monitor: applied.append(percent),
        apply_night_light=lambda percent: night_light.append(percent) or True,
    )
    return settings, service, applied, night_light


def test_service_applies_brightness_from_reading(tmp_path):
    FakeCamera.instances.clear()
    settings, service, applied, _ = make_service(tmp_path, lambda index: FakeCamera(index, (5.0,)))
    service.start()
    try:
        assert wait_for(lambda: applied)
        assert applied[0] == 50
        assert service.status.state == "running"
    finally:
        service.stop()


def test_disabling_releases_camera_and_pauses(tmp_path):
    FakeCamera.instances.clear()
    settings, service, applied, _ = make_service(tmp_path, lambda index: FakeCamera(index, (5.0,)))
    service.start()
    try:
        assert wait_for(lambda: applied)
        settings.update(enabled=False)
        assert wait_for(lambda: service.status.state == "disabled")
        assert FakeCamera.instances[0].closed
    finally:
        service.stop()


def test_camera_failure_is_reported_and_recovered(tmp_path):
    FakeCamera.instances.clear()
    attempts = []

    def factory(index):
        attempts.append(index)
        return FakeCamera(index, (5.0,), fail_open=len(attempts) == 1)

    settings, service, applied, _ = make_service(tmp_path, factory)
    import autobrightness.service as service_module

    original_delay = service_module.RETRY_DELAY_S
    service_module.RETRY_DELAY_S = 0.1
    service.start()
    try:
        assert wait_for(lambda: service.status.state == "error" or applied)
        assert wait_for(lambda: applied)
    finally:
        service_module.RETRY_DELAY_S = original_delay
        service.stop()


def test_calibration_takes_current_exposure_value(tmp_path):
    FakeCamera.instances.clear()
    settings, service, applied, _ = make_service(tmp_path, lambda index: FakeCamera(index, (3.37,)))
    service.start()
    try:
        assert wait_for(lambda: applied)
        assert service.calibrate(dark=True)
        assert settings.snapshot().dark_exposure_value == 3.37
    finally:
        service.stop()


def test_night_light_applied_and_reset_on_stop(tmp_path):
    FakeCamera.instances.clear()
    settings, service, applied, night_light = make_service(
        tmp_path, lambda index: FakeCamera(index, (5.0,)), night_shift_percent=40
    )
    service.start()
    assert wait_for(lambda: 40 in night_light)
    service.stop()
    assert night_light[-1] == 0
