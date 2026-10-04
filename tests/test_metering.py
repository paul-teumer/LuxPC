import numpy as np
import pytest

from luxpc import metering


def gray_frame(level: float) -> np.ndarray:
    return np.full((120, 160), round(level * 255), dtype=np.uint8)


def simulated_level(scene_luminance: float, exposure_log2_seconds: int) -> float:
    """Kamera-Modell: linear * Belichtungszeit, Gamma, Sättigung."""
    linear = min(1.0, scene_luminance * 2.0**exposure_log2_seconds)
    return linear ** (1 / metering.CAMERA_GAMMA)


def test_exposure_value_is_independent_of_exposure_time():
    scene_luminance = 150.0
    values = []
    for exposure in (-10, -9, -8):
        statistics = metering.frame_statistics(gray_frame(simulated_level(scene_luminance, exposure)))
        values.append(metering.exposure_value(statistics.linear_level, exposure))
    assert max(values) - min(values) < 0.15


def test_doubling_the_light_adds_one_stop():
    low = metering.frame_statistics(gray_frame(simulated_level(10.0, -6)))
    high = metering.frame_statistics(gray_frame(simulated_level(20.0, -6)))
    difference = metering.exposure_value(high.linear_level, -6) - metering.exposure_value(low.linear_level, -6)
    assert difference == pytest.approx(1.0, abs=0.1)


def test_overexposed_frame_shortens_exposure():
    statistics = metering.frame_statistics(gray_frame(1.0))
    assert metering.next_exposure(statistics, -4, -10, -2) < -4


def test_underexposed_frame_lengthens_exposure():
    statistics = metering.frame_statistics(gray_frame(0.05))
    assert metering.next_exposure(statistics, -8, -10, -2) > -8


def test_well_exposed_frame_keeps_exposure():
    statistics = metering.frame_statistics(gray_frame(0.5))
    assert metering.next_exposure(statistics, -6, -10, -2) == -6


def test_exposure_is_limited_to_camera_range():
    assert metering.next_exposure(metering.frame_statistics(gray_frame(1.0)), -10, -10, -2) == -10
    assert metering.next_exposure(metering.frame_statistics(gray_frame(0.02)), -2, -10, -2) == -2


def test_control_loop_converges_for_any_scene():
    minimum, maximum = -10, -2
    for scene_luminance in (0.5, 5, 50, 500, 5000):
        exposure = -6
        for _ in range(8):
            statistics = metering.frame_statistics(gray_frame(simulated_level(scene_luminance, exposure)))
            exposure = metering.next_exposure(statistics, exposure, minimum, maximum)
        statistics = metering.frame_statistics(gray_frame(simulated_level(scene_luminance, exposure)))
        assert metering.reading_is_reliable(statistics, exposure, minimum, maximum)


def test_limit_reading_is_reliable_only_at_the_limit():
    saturated = metering.frame_statistics(gray_frame(1.0))
    assert metering.reading_is_reliable(saturated, -10, -10, -2)
    assert not metering.reading_is_reliable(saturated, -6, -10, -2)
