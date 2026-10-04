import json

from autobrightness.config import Settings, SettingsData, sanitize


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
    assert loaded.measure_interval_s == 0.3


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
    data = sanitize(SettingsData(min_brightness_percent=80, max_brightness_percent=20, dark_exposure_value=5, bright_exposure_value=5))
    assert data.max_brightness_percent >= data.min_brightness_percent
    assert data.bright_exposure_value - data.dark_exposure_value >= 1.0


def test_listeners_are_notified(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    calls = []
    settings.subscribe(lambda: calls.append(1))
    settings.update(enabled=False)
    assert calls == [1]
