"""Programmstart: Dienst, Infobereich-Symbol und Einstellungsfenster."""

from __future__ import annotations

import ctypes
import sys

import pystray

from .config import Settings
from .icon import render_icon, system_icon_sizes
from .service import BrightnessService
from .ui import SettingsWindow

MUTEX_NAME = "Local\\AutoBrightnessSingleInstance"
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main() -> int:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # echte Pixelgrößen für Symbole, keine Skalierung durch Windows
    if acquire_single_instance() is None:
        return 0

    settings = Settings()
    service = BrightnessService(settings)
    service.start()

    window: SettingsWindow

    def quit_application() -> None:
        tray.stop()
        window.quit()

    window = SettingsWindow(settings, service, on_quit=quit_application)

    def toggle_enabled() -> None:
        settings.update(enabled=not settings.snapshot().enabled)

    menu = pystray.Menu(
        pystray.MenuItem("Einstellungen öffnen", lambda: window.post(window.show), default=True),
        pystray.MenuItem(
            "Automatik aktiv", toggle_enabled, checked=lambda item: settings.snapshot().enabled
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Beenden", lambda: window.post(quit_application)),
    )
    tray = pystray.Icon("AutoBrightness", render_icon(system_icon_sizes()[0]), "AutoBrightness", menu)
    tray.run_detached()

    if "--minimized" in sys.argv:
        window.hide()
    try:
        window.mainloop()
    finally:
        tray.stop()
        service.stop()
    return 0
