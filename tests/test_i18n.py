import pytest

from luxpc import i18n
from luxpc.config import Settings
from luxpc.service import Status
from luxpc.ui import describe_status


def test_all_languages_define_the_same_keys():
    assert set(i18n.TEXTS["de"]) == set(i18n.TEXTS["en"])


@pytest.mark.parametrize("language", i18n.LANGUAGES)
def test_placeholders_match_between_languages(language):
    for key, text in i18n.TEXTS[language].items():
        assert text.count("{") == i18n.TEXTS["en"][key].count("{"), key


def test_explicit_language_is_used():
    i18n.set_language("de")
    assert i18n.translate("status.active") == "Aktiv"
    i18n.set_language("en")
    assert i18n.translate("status.active") == "Active"


def test_automatic_language_follows_system(monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "de")
    i18n.set_language(i18n.AUTOMATIC)
    assert i18n.translate("status.paused") == "Pausiert"


def test_status_text_is_translated():
    i18n.set_language("en")
    assert describe_status(Status(state="busy", message="Zoom.exe")) == ("Paused · Zoom.exe", False)
    assert describe_status(Status(state="brightness_error", message="x")) == ("Cannot set brightness: x", True)


def test_unknown_language_setting_falls_back_to_automatic(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "fr"}', encoding="utf-8")
    assert Settings(path).snapshot().language == i18n.AUTOMATIC


def test_reset_keeps_language(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    settings.update(language="en", min_brightness_percent=40)
    settings.reset()
    assert settings.snapshot().language == "en"
    assert settings.snapshot().min_brightness_percent == 0
