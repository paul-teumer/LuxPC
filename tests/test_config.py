import json

import pytest

from autobrightness.config import MIN_POINT_DISTANCE, Settings, SettingsData, sanitize


def test_defaults_when_file_missing(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    assert settings.snapshot() == SettingsData()


def test_update_persists_and_reloads(tmp_path):
    path = tmp_path / "settings.json"
    Settings(path).update(min_brightness_percent=25, monitor="Dell")
    reloaded = Settings(path).snapshot()
    assert reloaded.min_brightness_percent == 25
    assert reloaded.monitor == "Dell"


def test_out_of_range_values_are_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"night_shift_percent": 500, "measure_interval_s": 0}), encoding="utf-8")
    loaded = Settings(path).snapshot()
    assert loaded.night_shift_percent == 100
    assert loaded.measure_interval_s == 2.0


def test_corrupt_file_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{kaputt", encoding="utf-8")
    assert Settings(path).snapshot() == SettingsData()
    path.write_text(json.dumps({"unbekannt": 1, "enabled": False}), encoding="utf-8")
    assert Settings(path).snapshot().enabled is False


def test_wrong_types_fall_back_to_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hysteresis_percent": "viel"}), encoding="utf-8")
    assert Settings(path).snapshot().hysteresis_percent == SettingsData().hysteresis_percent


def test_sanitize_keeps_ranges_consistent():
    data = sanitize(SettingsData(min_brightness_percent=80, max_brightness_percent=20))
    assert data.max_brightness_percent >= data.min_brightness_percent


def test_sanitize_sorts_merges_and_limits_calibration_points():
    data = sanitize(SettingsData(calibration_points=[[8, 120], [2, 30], [2.05, 40], [-50, 10]]))
    assert data.calibration_points == [[-30.0, 10.0], [2.05, 40.0], [8.0, 100.0]]
    assert all(b[0] - a[0] >= MIN_POINT_DISTANCE for a, b in zip(data.calibration_points, data.calibration_points[1:]))


def test_sanitize_restores_default_for_too_few_or_invalid_points():
    assert sanitize(SettingsData(calibration_points=[[1, 1]])).calibration_points == SettingsData().calibration_points
    assert sanitize(SettingsData(calibration_points="x")).calibration_points == SettingsData().calibration_points


def test_calibration_points_roundtrip_and_legacy_migration(tmp_path):
    path = tmp_path / "settings.json"
    Settings(path).update(calibration_points=[[0, 5], [3, 50], [9, 90]])
    assert Settings(path).snapshot().calibration_points == [[0.0, 5.0], [3.0, 50.0], [9.0, 90.0]]
    path.write_text(json.dumps({"dark_exposure_value": -2.0, "bright_exposure_value": 6.0, "min_brightness_percent": 20}), encoding="utf-8")
    assert Settings(path).snapshot().calibration_points == [[-2.0, 20.0], [6.0, 100.0]]


def test_listeners_are_notified(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    calls = []
    settings.subscribe(lambda: calls.append(1))
    settings.update(enabled=False)
    assert calls == [1]


def test_default_calibration_points_form_a_sigmoid():
    points = SettingsData().calibration_points
    percents = [percent for _, percent in points]
    assert percents[0] == 10.0 and percents[-1] == 100.0
    assert percents == sorted(percents)
    steps = [b - a for a, b in zip(percents, percents[1:])]
    assert max(steps) in steps[2:4] and steps[0] < max(steps) > steps[-1]
    assert sanitize(SettingsData()).calibration_points == points
