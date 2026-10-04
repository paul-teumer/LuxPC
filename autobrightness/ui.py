"""Einstellungsfenster (customtkinter) mit Live-Anzeige."""

from __future__ import annotations

import queue
import tkinter as tk
from typing import Callable, Optional

import customtkinter

from . import __version__, display, startup
from .config import Settings
from .icon import render_icon
from .service import BrightnessService, Status

ACCENT = "#F5A524"
ACCENT_HOVER = "#D98E12"
CARD_COLOR = ("#FFFFFF", "#1F2430")
WINDOW_COLOR = ("#EEF0F4", "#14171E")
MUTED_TEXT = ("#6B7280", "#8B93A4")
AMBIENT_LINE = ("#D98E12", "#F5A524")
BRIGHTNESS_LINE = ("#2563EB", "#60A5FA")
GRAPH_BACKGROUND = ("#F5F6F9", "#171A22")
GRAPH_GRID = ("#DADDE4", "#2A3040")
SAVE_DELAY_MS = 250
REFRESH_MS = 500
MIN_GRAPH_SAMPLES = 60
AUTO_MONITOR_LABEL = "Alle Bildschirme"


def format_shutter(exposure_log2_seconds: Optional[int]) -> str:
    if exposure_log2_seconds is None:
        return "–"
    denominator = 2 ** -exposure_log2_seconds
    return f"1/{denominator} s" if denominator > 1 else f"{2 ** exposure_log2_seconds} s"


def describe_status(status: Status) -> tuple[str, bool]:
    """(Text, ist_Warnung)."""
    if status.state == "disabled":
        return "Automatik pausiert – Kamera ist frei", False
    if status.state == "error":
        return f"{status.message} – neuer Versuch folgt", True
    if status.state == "starting":
        return "Starte Messung …", False
    if not status.exposure_control_available:
        return "Kamera ohne Belichtungssteuerung – Messung ungenau", True
    if not status.reliable:
        return "Messgrenze der Kamera erreicht", True
    return "Aktiv", False


def _color(pair: tuple[str, str]) -> str:
    return pair[1] if customtkinter.get_appearance_mode() == "Dark" else pair[0]


class SettingsWindow(customtkinter.CTk):
    def __init__(
        self,
        settings: Settings,
        service: BrightnessService,
        on_quit: Callable[[], None],
    ) -> None:
        customtkinter.set_appearance_mode("system")
        customtkinter.set_default_color_theme("blue")
        super().__init__(fg_color=WINDOW_COLOR)
        self._settings = settings
        self._service = service
        self._on_quit = on_quit
        self._commands: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._pending_saves: dict[str, str] = {}
        self._value_labels: dict[str, customtkinter.CTkLabel] = {}

        self.title("AutoBrightness")
        self.geometry("480x840")
        self.minsize(440, 560)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._icon_image = tk.PhotoImage(master=self, data=render_icon(64, png_base64=True))
        self.iconphoto(True, self._icon_image)

        self._build()
        self.after(REFRESH_MS, self._refresh)

    # ----- Aufbau -----

    def _card(self, title: str, subtitle: Optional[str] = None) -> customtkinter.CTkFrame:
        card = customtkinter.CTkFrame(self._body, fg_color=CARD_COLOR, corner_radius=14)
        card.pack(fill="x", padx=16, pady=(0, 12))
        customtkinter.CTkLabel(
            card, text=title, font=customtkinter.CTkFont(size=15, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(14, 0 if subtitle else 8))
        if subtitle:
            customtkinter.CTkLabel(
                card, text=subtitle, text_color=MUTED_TEXT, anchor="w", justify="left",
                wraplength=380, font=customtkinter.CTkFont(size=12),
            ).pack(fill="x", padx=18, pady=(0, 8))
        return card

    def _build(self) -> None:
        data = self._settings.snapshot()

        header = customtkinter.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 10))
        customtkinter.CTkLabel(
            header, text="☀  AutoBrightness", text_color=ACCENT,
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(side="left")
        self._enabled_switch = customtkinter.CTkSwitch(
            header, text="Automatik", progress_color=ACCENT, command=self._toggle_enabled,
        )
        self._enabled_switch.pack(side="right")
        if data.enabled:
            self._enabled_switch.select()

        self._body = customtkinter.CTkScrollableFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True)

        live = self._card("Live")
        self._brightness_label = customtkinter.CTkLabel(
            live, text="–", text_color=ACCENT, font=customtkinter.CTkFont(size=44, weight="bold")
        )
        self._brightness_label.pack(pady=(0, 0))
        self._ambient_label = customtkinter.CTkLabel(
            live, text="Bildschirmhelligkeit", text_color=MUTED_TEXT
        )
        self._ambient_label.pack()
        self._ambient_bar = customtkinter.CTkProgressBar(live, progress_color=ACCENT, height=10)
        self._ambient_bar.set(0)
        self._ambient_bar.pack(fill="x", padx=18, pady=(14, 2))
        scale = customtkinter.CTkFrame(live, fg_color="transparent")
        scale.pack(fill="x", padx=18)
        customtkinter.CTkLabel(scale, text="dunkel", text_color=MUTED_TEXT, font=customtkinter.CTkFont(size=11)).pack(side="left")
        customtkinter.CTkLabel(scale, text="hell", text_color=MUTED_TEXT, font=customtkinter.CTkFont(size=11)).pack(side="right")
        self._detail_label = customtkinter.CTkLabel(live, text="", text_color=MUTED_TEXT, font=customtkinter.CTkFont(size=12))
        self._detail_label.pack(pady=(6, 4))
        self._graph = tk.Canvas(live, height=90, highlightthickness=0, bd=0)
        self._graph.pack(fill="x", padx=18, pady=(4, 8))
        self._status_label = customtkinter.CTkLabel(live, text="", anchor="center")
        self._status_label.pack(pady=(0, 14))

        calibration = self._card(
            "Kalibrierung",
            "Stelle die gewünschte Umgebung her und übernimm sie: bei der dunkelsten Umgebung "
            "wird die minimale, bei der hellsten die maximale Helligkeit verwendet.",
        )
        buttons = customtkinter.CTkFrame(calibration, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 6))
        buttons.columnconfigure((0, 1), weight=1)
        customtkinter.CTkButton(
            buttons, text="Jetzt = dunkel", fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#1B1B1B", command=lambda: self._calibrate(True),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        customtkinter.CTkButton(
            buttons, text="Jetzt = hell", fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#1B1B1B", command=lambda: self._calibrate(False),
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")
        self._calibration_label = customtkinter.CTkLabel(
            calibration, text="", text_color=MUTED_TEXT, font=customtkinter.CTkFont(size=12)
        )
        self._calibration_label.pack(pady=(0, 14))

        range_card = self._card("Helligkeitsbereich")
        self._add_slider(range_card, "min_brightness_percent", "Minimum", 0, 100, data, lambda value: f"{int(value)} %", steps=100)
        self._add_slider(range_card, "max_brightness_percent", "Maximum", 0, 100, data, lambda value: f"{int(value)} %", steps=100)
        self._add_slider(range_card, "brightness_offset_percent", "Versatz", -30, 30, data, lambda value: f"{int(value):+d} %", steps=60)
        customtkinter.CTkFrame(range_card, height=6, fg_color="transparent").pack()

        behaviour = self._card("Verhalten")
        self._add_slider(behaviour, "response_time_s", "Trägheit", 0, 30, data, lambda value: f"{value:.0f} s", steps=30)
        self._add_slider(behaviour, "measure_interval_s", "Messintervall", 0.3, 10, data, lambda value: f"{value:.1f} s", steps=97)
        self._add_slider(behaviour, "hysteresis_percent", "Mindeständerung", 0, 10, data, lambda value: f"{int(value)} %", steps=10)
        customtkinter.CTkFrame(behaviour, height=6, fg_color="transparent").pack()

        screen = self._card("Bildschirm")
        monitors = [AUTO_MONITOR_LABEL] + display.list_monitors()
        self._monitor_menu = customtkinter.CTkOptionMenu(
            screen, values=monitors, command=self._select_monitor,
            fg_color=("#E4E7EE", "#2A3040"), button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            text_color=("#1B1B1B", "#E8EAF0"),
        )
        self._monitor_menu.set(data.monitor if data.monitor in monitors else AUTO_MONITOR_LABEL)
        self._monitor_menu.pack(fill="x", padx=18, pady=(0, 6))
        self._add_slider(screen, "night_shift_percent", "Nachtlicht", 0, 100, data, lambda value: f"{int(value)} %", steps=100)
        customtkinter.CTkFrame(screen, height=6, fg_color="transparent").pack()

        system = self._card("System")
        self._autostart_switch = customtkinter.CTkSwitch(
            system, text="Mit Windows starten", progress_color=ACCENT, command=self._toggle_autostart
        )
        self._autostart_switch.pack(anchor="w", padx=18, pady=(0, 10))
        if startup.is_enabled():
            self._autostart_switch.select()
        customtkinter.CTkButton(
            system, text="Beenden", fg_color=("#E4E7EE", "#2A3040"), hover_color=("#D5D9E2", "#363D52"),
            text_color=("#1B1B1B", "#E8EAF0"), command=self._on_quit,
        ).pack(fill="x", padx=18, pady=(0, 14))

        customtkinter.CTkLabel(
            self._body, text=f"Version {__version__}", text_color=MUTED_TEXT, font=customtkinter.CTkFont(size=11)
        ).pack(pady=(0, 14))

    def _add_slider(self, parent, key, label, minimum, maximum, data, formatter, steps) -> None:
        row = customtkinter.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=2)
        row.columnconfigure(1, weight=1)
        customtkinter.CTkLabel(row, text=label, width=110, anchor="w").grid(row=0, column=0)
        value_label = customtkinter.CTkLabel(row, text="", width=54, anchor="e", text_color=MUTED_TEXT)
        value_label.grid(row=0, column=2)
        self._value_labels[key] = value_label

        def on_change(value: float) -> None:
            value_label.configure(text=formatter(value))
            self._schedule_save(key, value)

        slider = customtkinter.CTkSlider(
            row, from_=minimum, to=maximum, number_of_steps=steps,
            progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            command=on_change,
        )
        slider.set(getattr(data, key))
        slider.grid(row=0, column=1, sticky="ew", padx=8)
        value_label.configure(text=formatter(getattr(data, key)))

    # ----- Einstellungen schreiben -----

    def _schedule_save(self, key: str, value: float) -> None:
        current = getattr(self._settings.snapshot(), key)
        converted = type(current)(round(value) if isinstance(current, int) else value)
        if key in self._pending_saves:
            self.after_cancel(self._pending_saves[key])
        self._pending_saves[key] = self.after(
            SAVE_DELAY_MS, lambda: self._commit(key, converted)
        )

    def _commit(self, key: str, value) -> None:
        self._pending_saves.pop(key, None)
        self._settings.update(**{key: value})

    def _toggle_enabled(self) -> None:
        self._settings.update(enabled=bool(self._enabled_switch.get()))

    def _toggle_autostart(self) -> None:
        startup.set_enabled(bool(self._autostart_switch.get()))

    def _select_monitor(self, choice: str) -> None:
        self._settings.update(monitor=None if choice == AUTO_MONITOR_LABEL else choice)

    def _calibrate(self, dark: bool) -> None:
        self._service.calibrate(dark)

    # ----- Fenstersteuerung (threadsicher über Warteschlange) -----

    def post(self, command: Callable[[], None]) -> None:
        self._commands.put(command)

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        self.withdraw()

    def sync_enabled_switch(self) -> None:
        if self._settings.snapshot().enabled:
            self._enabled_switch.select()
        else:
            self._enabled_switch.deselect()

    # ----- Live-Anzeige -----

    def _refresh(self) -> None:
        while True:
            try:
                self._commands.get_nowait()()
            except queue.Empty:
                break
        if self.state() != "withdrawn":
            self._update_live()
        self.after(REFRESH_MS, self._refresh)

    def _update_live(self) -> None:
        status = self._service.status
        data = self._settings.snapshot()
        text, warning = describe_status(status)
        self._status_label.configure(text=text, text_color="#E5484D" if warning else "#30A46C")
        self.sync_enabled_switch()

        if status.exposure_value is None:
            self._brightness_label.configure(text="–")
            self._detail_label.configure(text="")
            self._ambient_bar.set(0)
        else:
            self._brightness_label.configure(text=f"{status.applied_percent} %")
            self._detail_label.configure(
                text=f"Umgebungslicht {status.exposure_value:.1f} EV  ·  Belichtung {format_shutter(status.exposure_log2_seconds)}"
            )
            span = data.bright_exposure_value - data.dark_exposure_value
            self._ambient_bar.set(max(0.0, min(1.0, (status.exposure_value - data.dark_exposure_value) / span)))
        self._calibration_label.configure(
            text=f"dunkel {data.dark_exposure_value:.1f} EV   ·   hell {data.bright_exposure_value:.1f} EV"
        )
        self._draw_graph(data)

    def _draw_graph(self, data) -> None:
        canvas = self._graph
        canvas.configure(bg=_color(GRAPH_BACKGROUND))
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 50), max(canvas.winfo_height(), 50)
        for fraction in (0.25, 0.5, 0.75):
            canvas.create_line(0, height * fraction, width, height * fraction, fill=_color(GRAPH_GRID))
        history = list(self._service.history)
        if len(history) < 2:
            return
        low = min(data.dark_exposure_value, min(entry[1] for entry in history)) - 0.5
        high = max(data.bright_exposure_value, max(entry[1] for entry in history)) + 0.5
        step = width / (max(len(history), MIN_GRAPH_SAMPLES) - 1)

        def line(values: list[float], color: str) -> None:
            points = []
            for index, value in enumerate(values):
                points += [index * step, height - 6 - value * (height - 12)]
            canvas.create_line(*points, fill=color, width=2, smooth=True)

        line([(entry[1] - low) / (high - low) for entry in history], _color(AMBIENT_LINE))
        line([entry[2] / 100 for entry in history], _color(BRIGHTNESS_LINE))
