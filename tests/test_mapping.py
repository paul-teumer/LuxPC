import math

import pytest

from autobrightness import mapping
from autobrightness.config import SettingsData


def settings(**changes) -> SettingsData:
    return SettingsData(
        dark_exposure_value=0.0,
        bright_exposure_value=10.0,
        min_brightness_percent=10,
        max_brightness_percent=90,
        **changes,
    )


def test_mapping_endpoints_and_clamping():
    assert mapping.target_brightness(-5, settings()) == 10
    assert mapping.target_brightness(0, settings()) == 10
    assert mapping.target_brightness(10, settings()) == 90
    assert mapping.target_brightness(20, settings()) == 90


def test_mapping_is_linear_in_stops():
    assert mapping.target_brightness(5, settings()) == pytest.approx(50)


def test_offset_shifts_and_stays_within_percent_range():
    assert mapping.target_brightness(5, settings(brightness_offset_percent=10)) == pytest.approx(60)
    assert mapping.target_brightness(10, settings(brightness_offset_percent=30)) == 100
    assert mapping.target_brightness(0, settings(brightness_offset_percent=-30)) == 0


def test_smoother_first_sample_is_taken_over():
    smoother = mapping.ExposureValueSmoother()
    assert smoother.advance(1.0, 4.0) is None
    smoother.set_sample(5.0)
    assert smoother.advance(1.0, 4.0) == 5.0


def test_smoother_follows_time_constant():
    smoother = mapping.ExposureValueSmoother()
    smoother.set_sample(0.0)
    smoother.advance(1.0, 4.0)
    smoother.set_sample(10.0)
    assert smoother.advance(4.0, 4.0) == pytest.approx(10 * (1 - math.exp(-1)), abs=1e-6)


def test_smoother_is_step_size_independent():
    coarse = mapping.ExposureValueSmoother()
    fine = mapping.ExposureValueSmoother()
    for smoother in (coarse, fine):
        smoother.set_sample(0.0)
        smoother.advance(1.0, 4.0)
        smoother.set_sample(10.0)
    coarse_value = coarse.advance(2.0, 4.0)
    for _ in range(4):
        fine_value = fine.advance(0.5, 4.0)
    assert coarse_value == pytest.approx(fine_value, abs=1e-6)


def test_zero_response_time_disables_smoothing():
    smoother = mapping.ExposureValueSmoother()
    smoother.set_sample(0.0)
    smoother.advance(1.0, 0.0)
    smoother.set_sample(7.0)
    assert smoother.advance(1.0, 0.0) == 7.0


@pytest.mark.parametrize(
    "candidate, last, hysteresis, expected",
    [(50, None, 3, True), (51, 50, 3, False), (53, 50, 3, True), (50, 50, 3, False), (100, 99, 3, True), (0, 1, 3, True)],
)
def test_hysteresis(candidate, last, hysteresis, expected):
    assert mapping.should_apply(candidate, last, hysteresis) is expected
