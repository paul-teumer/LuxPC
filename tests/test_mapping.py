import math

import pytest

from autobrightness import mapping
from autobrightness.config import SettingsData


def settings(**changes) -> SettingsData:
    return SettingsData(
        calibration_points=[[0.0, 10.0], [10.0, 90.0]],
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


def test_curve_follows_multiple_points():
    data = SettingsData(calibration_points=[[0.0, 5.0], [4.0, 20.0], [10.0, 100.0]], min_brightness_percent=0)
    assert mapping.target_brightness(4, data) == pytest.approx(20)
    assert mapping.target_brightness(2, data) == pytest.approx(12.5)
    assert mapping.target_brightness(7, data) == pytest.approx(60)


def test_offset_shifts_and_stays_within_limits():
    assert mapping.target_brightness(5, settings(brightness_offset_percent=10)) == pytest.approx(60)
    assert mapping.target_brightness(10, settings(brightness_offset_percent=30)) == 90
    assert mapping.target_brightness(0, settings(brightness_offset_percent=-30)) == 10


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


def test_ramp_first_value_is_target():
    assert mapping.BrightnessRamp().next_value(49.6, 3) == 50


def test_ramp_ignores_deviation_below_hysteresis():
    assert mapping.BrightnessRamp(50).next_value(52.0, 3) is None


def test_ramp_moves_in_single_steps_until_target_is_reached():
    ramp = mapping.BrightnessRamp(50)
    values = []
    while (value := ramp.next_value(54.0, 3)) is not None:
        values.append(value)
        ramp.applied = value
    assert values == [51, 52, 53, 54]
    assert ramp.next_value(55.0, 3) is None


def test_ramp_always_reaches_limits():
    assert mapping.BrightnessRamp(99).next_value(100.0, 3) == 100
    assert mapping.BrightnessRamp(1).next_value(0.0, 3) == 0


def test_ramp_step_grows_with_distance_but_stays_a_fraction_of_it():
    assert mapping.BrightnessRamp(0).next_value(100.0, 0) == 25
    assert mapping.BrightnessRamp(100).next_value(0.0, 0) == 75
