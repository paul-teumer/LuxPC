import time

import autobrightness.service as service_module
from autobrightness.camera import CameraError, CameraInUseError, Reading
from autobrightness.config import Settings
from autobrightness.service import BrightnessService


class FakeCamera:
    def __init__(self, exposure_value: float = 5.0, fail_open_times: int = 0) -> None:
        self.exposure_value = exposure_value
        self.fail_open_times = fail_open_times
        self.open_count = self.close_count = 0
        self.is_open = False

    def open(self) -> None:
        if self.fail_open_times > 0:
            self.fail_open_times -= 1
            raise CameraError("belegt")
        self.open_count += 1
        self.is_open = True

    def measure(self, is_camera_free=lambda: True) -> Reading:
        assert self.is_open
        if not is_camera_free():
            raise CameraInUseError("belegt")
        return Reading(self.exposure_value, -8, 0.5, True, True)

    def close(self) -> None:
        self.close_count += 1
        self.is_open = False


def wait_for(condition, timeout=4.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def make_service(tmp_path, camera, camera_users=lambda: [], current_brightness=None, **settings_changes):
    settings = Settings(tmp_path / "settings.json")
    settings.update(
        response_time_s=0.0, dark_exposure_value=0.0, bright_exposure_value=10.0,
        min_brightness_percent=0, max_brightness_percent=100, **settings_changes,
    )
    applied, night_light = [], []
    service = BrightnessService(
        settings, lambda index: camera,
        set_brightness=lambda percent, monitor: applied.append(percent),
        get_brightness=lambda monitor: current_brightness,
        apply_night_light=lambda percent: night_light.append(percent) or True,
        find_camera_users=camera_users,
    )
    return settings, service, applied, night_light


def test_service_applies_brightness_from_reading(tmp_path):
    camera = FakeCamera(5.0)
    _, service, applied, _ = make_service(tmp_path, camera)
    service.start()
    try:
        assert wait_for(lambda: applied)
        assert applied[0] == 50
        assert service.status.state == "running"
    finally:
        service.stop()


def test_camera_is_released_between_measurements(tmp_path):
    camera = FakeCamera(5.0)
    _, service, applied, _ = make_service(tmp_path, camera)
    service.start()
    try:
        assert wait_for(lambda: applied)
        time.sleep(0.3)
        assert not camera.is_open
        assert camera.open_count == 1 and camera.close_count >= 1
    finally:
        service.stop()


def test_measurement_is_skipped_while_another_application_uses_the_camera(tmp_path):
    camera = FakeCamera(5.0)
    _, service, applied, _ = make_service(tmp_path, camera, camera_users=lambda: ["Zoom.exe"])
    service.start()
    try:
        assert wait_for(lambda: service.status.state == "busy")
        assert service.status.message == "Zoom.exe"
        time.sleep(0.5)
        assert camera.open_count == 0 and not applied
    finally:
        service.stop()


def test_measurement_resumes_after_other_application_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "RETRY_DELAY_S", 0.1)
    users = ["Teams.exe"]
    camera = FakeCamera(5.0)
    _, service, applied, _ = make_service(tmp_path, camera, camera_users=lambda: users)
    service.start()
    try:
        assert wait_for(lambda: service.status.state == "busy")
        users.clear()
        assert wait_for(lambda: applied)
        assert service.status.state == "running"
    finally:
        service.stop()


def test_busy_camera_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "RETRY_DELAY_S", 0.1)
    camera = FakeCamera(5.0, fail_open_times=1)
    _, service, applied, _ = make_service(tmp_path, camera)
    service.start()
    try:
        assert wait_for(lambda: service.status.state == "busy")
        assert wait_for(lambda: applied)
    finally:
        service.stop()


def test_disabling_pauses_without_touching_camera(tmp_path):
    camera = FakeCamera(5.0)
    settings, service, applied, _ = make_service(tmp_path, camera)
    service.start()
    try:
        assert wait_for(lambda: applied)
        settings.update(enabled=False)
        assert wait_for(lambda: service.status.state == "disabled")
        opened = camera.open_count
        time.sleep(0.4)
        assert camera.open_count == opened and not camera.is_open
    finally:
        service.stop()


def test_calibration_takes_latest_raw_measurement(tmp_path):
    camera = FakeCamera(3.37)
    settings, service, applied, _ = make_service(tmp_path, camera)
    service.start()
    try:
        assert wait_for(lambda: applied)
        assert service.calibrate(dark=True)
        assert settings.snapshot().dark_exposure_value == 3.37
    finally:
        service.stop()


def test_brightness_ramps_between_measurements(tmp_path):
    camera = FakeCamera(0.0)
    settings, service, applied, _ = make_service(tmp_path, camera, measure_interval_s=2.0, hysteresis_percent=0)
    settings.update(response_time_s=2.0)
    service.start()
    try:
        assert wait_for(lambda: applied)
        camera.exposure_value = 10.0
        assert wait_for(lambda: len(applied) >= 4, timeout=12.0)
        assert applied == sorted(applied) and len(set(applied)) > 2
    finally:
        service.stop()


def test_night_light_applied_and_reset_on_stop(tmp_path):
    _, service, _, night_light = make_service(tmp_path, FakeCamera(5.0), night_shift_percent=40)
    service.start()
    assert wait_for(lambda: 40 in night_light)
    service.stop()
    assert night_light[-1] == 0


def test_brightness_starts_at_current_value_and_approaches_target_without_jumping(tmp_path):
    _, service, applied, _ = make_service(tmp_path, FakeCamera(5.0), current_brightness=0)
    service.start()
    try:
        assert wait_for(lambda: applied and applied[-1] == 50)
        assert applied[0] <= 13 and applied == sorted(applied) and len(applied) >= 5
    finally:
        service.stop()


def test_measurement_is_aborted_and_camera_released_when_another_application_starts_midway(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "RETRY_DELAY_S", 0.1)
    answers = iter([[], ["Zoom.exe"]])
    camera = FakeCamera(5.0)
    _, service, applied, _ = make_service(tmp_path, camera, camera_users=lambda: next(answers, ["Zoom.exe"]))
    service.start()
    try:
        assert wait_for(lambda: service.status.state == "busy" and camera.close_count >= 1)
        assert service.status.message == "Zoom.exe"
        assert not camera.is_open and not applied
    finally:
        service.stop()
