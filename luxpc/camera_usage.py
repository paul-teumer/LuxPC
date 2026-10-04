"""Erkennt Programme, die die Kamera gerade verwenden (Windows-Datenschutzprotokoll)."""

from __future__ import annotations

import ntpath
import sys
import winreg
from typing import Iterator, Optional

CONSENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
NON_PACKAGED = "NonPackaged"


def _subkeys(path: str) -> Iterator[str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                yield winreg.EnumKey(key, index)
    except OSError:
        return


def _is_in_use(path: str) -> bool:
    """Laufende Nutzung erkennt man an LastUsedTimeStop == 0."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "LastUsedTimeStop")[0] == 0
    except OSError:
        return False


def _display_name(entry: str) -> str:
    """Aus 'C:#Programme#Zoom#Zoom.exe' bzw. 'MSTeams_8wekyb3d8bbwe' einen lesbaren Namen machen."""
    if "#" in entry:
        return ntpath.basename(entry.replace("#", "\\"))
    return entry.split("_")[0]


def own_entry_name() -> str:
    return sys.executable.replace("\\", "#").lower()


def applications_using_camera(excluded_entry: Optional[str] = None) -> list[str]:
    """Namen der Programme, die die Kamera gerade verwenden (ohne die eigene Anwendung)."""
    excluded = (excluded_entry if excluded_entry is not None else own_entry_name()).lower()
    active = []
    for entry in _subkeys(CONSENT_KEY):
        if entry == NON_PACKAGED:
            for child in _subkeys(f"{CONSENT_KEY}\\{NON_PACKAGED}"):
                if child.lower() != excluded and _is_in_use(f"{CONSENT_KEY}\\{NON_PACKAGED}\\{child}"):
                    active.append(_display_name(child))
        elif _is_in_use(f"{CONSENT_KEY}\\{entry}"):
            active.append(_display_name(entry))
    return active
