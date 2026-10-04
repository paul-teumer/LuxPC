"""Übersetzungen der Benutzeroberfläche (Deutsch, Englisch)."""

from __future__ import annotations

import ctypes

LANGUAGES = ("de", "en")
AUTOMATIC = "auto"
FALLBACK_LANGUAGE = "en"

TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "tray.open": "Einstellungen öffnen",
        "tray.enabled": "Automatik aktiv",
        "tray.quit": "Beenden",
        "status.paused": "Pausiert",
        "status.paused_by": "Pausiert · {users}",
        "status.camera_busy": "Kamera belegt",
        "status.starting": "Starte …",
        "status.imprecise": "Messung ungenau",
        "status.limit_reached": "Messgrenze erreicht",
        "status.active": "Aktiv",
        "status.brightness_error": "Helligkeit nicht setzbar: {detail}",
        "card.range": "Helligkeitsbereich",
        "card.behaviour": "Verhalten",
        "card.screen": "Bildschirm",
        "card.calibration": "Kalibrierung",
        "slider.minimum": "Minimum",
        "slider.maximum": "Maximum",
        "slider.offset": "Versatz",
        "slider.response_time": "Trägheit",
        "slider.measure_interval": "Messintervall",
        "slider.hysteresis": "Mindeständerung",
        "slider.night_shift": "Nachtlicht",
        "monitor.all": "Alle Bildschirme",
        "live.dark": "dunkel",
        "live.bright": "hell",
        "live.ambient": "Umgebungslicht",
        "live.screen": "Bildschirm",
        "live.ambient_value": "Umgebungslicht {value} EV",
        "live.exposure": "Belichtung {shutter}",
        "calibration.set_point": "Jetzt mit dieser Helligkeit als Punkt festlegen",
        "calibration.hint": (
            "Passende Helligkeit für das jetzige Licht einstellen und festlegen – beliebig oft "
            "bei verschiedenem Licht. Punkte lassen sich in der Kurve ziehen; ein Klick daneben setzt einen neuen."
        ),
        "calibration.points": "Kalibrierpunkte ({count})",
        "system.autostart": "Mit Windows starten",
        "system.reset": "Zurücksetzen",
        "system.reset_confirm": "Sicher?",
        "system.quit": "Beenden",
        "footer.version": "Version {version}",
        "footer.language": "Sprache",
        "language.automatic": "Automatisch",
        "duration.decimal_separator": ",",
    },
    "en": {
        "tray.open": "Open settings",
        "tray.enabled": "Automatic mode on",
        "tray.quit": "Quit",
        "status.paused": "Paused",
        "status.paused_by": "Paused · {users}",
        "status.camera_busy": "Camera in use",
        "status.starting": "Starting …",
        "status.imprecise": "Imprecise measurement",
        "status.limit_reached": "Measuring limit reached",
        "status.active": "Active",
        "status.brightness_error": "Cannot set brightness: {detail}",
        "card.range": "Brightness range",
        "card.behaviour": "Behavior",
        "card.screen": "Display",
        "card.calibration": "Calibration",
        "slider.minimum": "Minimum",
        "slider.maximum": "Maximum",
        "slider.offset": "Offset",
        "slider.response_time": "Response delay",
        "slider.measure_interval": "Measuring interval",
        "slider.hysteresis": "Minimum change",
        "slider.night_shift": "Night light",
        "monitor.all": "All displays",
        "live.dark": "dark",
        "live.bright": "bright",
        "live.ambient": "Ambient light",
        "live.screen": "Display",
        "live.ambient_value": "Ambient light {value} EV",
        "live.exposure": "Exposure {shutter}",
        "calibration.set_point": "Set this brightness as a point now",
        "calibration.hint": (
            "Set the brightness that suits the current light and confirm it – as often as you like "
            "under different light. Points can be dragged in the curve; a click elsewhere adds a new one."
        ),
        "calibration.points": "Calibration points ({count})",
        "system.autostart": "Start with Windows",
        "system.reset": "Reset",
        "system.reset_confirm": "Sure?",
        "system.quit": "Quit",
        "footer.version": "Version {version}",
        "footer.language": "Language",
        "language.automatic": "Automatic",
        "duration.decimal_separator": ".",
    },
}

LANGUAGE_NAMES = {"de": "Deutsch", "en": "English"}

_language = FALLBACK_LANGUAGE


def detect_system_language() -> str:
    """Sprache der Windows-Oberfläche, sofern unterstützt."""
    buffer = ctypes.create_unicode_buffer(85)
    if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
        language = buffer.value.split("-")[0].lower()
        if language in LANGUAGES:
            return language
    return FALLBACK_LANGUAGE


def set_language(setting: str) -> None:
    """Setzt die Sprache aus der Einstellung ("auto", "de" oder "en")."""
    global _language
    _language = setting if setting in LANGUAGES else detect_system_language()


def translate(key: str, **values) -> str:
    return TEXTS[_language][key].format(**values)
