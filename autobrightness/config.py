"""Persistente, threadsichere Einstellungen."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable, Optional


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "AutoBrightness" / "settings.json"


@dataclass
class SettingsData:
    enabled: bool = True
    camera_index: int = 0
    monitor: Optional[str] = None
    measure_interval_s: float = 1.0
    response_time_s: float = 4.0
    hysteresis_percent: int = 2
    dark_exposure_value: float = 1.0
    bright_exposure_value: float = 8.0
    min_brightness_percent: int = 10
    max_brightness_percent: int = 100
    brightness_offset_percent: int = 0
    night_shift_percent: int = 0


# (Minimum, Maximum) je numerischem Feld; Werte außerhalb werden begrenzt.
LIMITS: dict[str, tuple[float, float]] = {
    "camera_index": (0, 9),
    "measure_interval_s": (0.3, 10.0),
    "response_time_s": (0.0, 30.0),
    "hysteresis_percent": (0, 10),
    "dark_exposure_value": (-4.0, 12.0),
    "bright_exposure_value": (-4.0, 12.0),
    "min_brightness_percent": (0, 100),
    "max_brightness_percent": (0, 100),
    "brightness_offset_percent": (-30, 30),
    "night_shift_percent": (0, 100),
}


def sanitize(data: SettingsData) -> SettingsData:
    for name, (minimum, maximum) in LIMITS.items():
        current = getattr(data, name)
        clamped = max(minimum, min(maximum, current))
        setattr(data, name, type(current)(clamped))
    if data.max_brightness_percent < data.min_brightness_percent:
        data.max_brightness_percent = data.min_brightness_percent
    if data.bright_exposure_value - data.dark_exposure_value < 1.0:
        data.bright_exposure_value = data.dark_exposure_value + 1.0
    return data


class Settings:
    """Thread-sicherer Zugriff mit Speichern auf Platte und Änderungs-Listenern."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_config_path()
        self._lock = threading.RLock()
        self._data = SettingsData()
        self._listeners: list[Callable[[], None]] = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        known = {field.name: field for field in fields(SettingsData)}
        data = SettingsData()
        for name, value in raw.items():
            if name in known and isinstance(value, (int, float, str, bool, type(None))):
                try:
                    default = getattr(data, name)
                    setattr(data, name, value if default is None else type(default)(value))
                except (TypeError, ValueError):
                    pass
        with self._lock:
            self._data = sanitize(data)

    def save(self) -> None:
        with self._lock:
            payload = json.dumps(asdict(self._data), indent=2, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass

    def snapshot(self) -> SettingsData:
        with self._lock:
            return SettingsData(**asdict(self._data))

    def update(self, **changes) -> None:
        with self._lock:
            for name, value in changes.items():
                setattr(self._data, name, value)
            sanitize(self._data)
        self.save()
        for listener in list(self._listeners):
            listener()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)
