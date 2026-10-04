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

FONT_FAMILY = "Segoe UI"
ACCENT = "#FFB224"
ACCENT_HOVER = "#E39A0B"
ACCENT_TEXT = "#1A1405"
SUCCESS = "#3DD68C"
DANGER = "#FF6369"
WINDOW_COLOR = ("#EDEFF4", "#0E1117")
CARD_COLOR = ("#FFFFFF", "#171B24")
CARD_BORDER = ("#DFE3EB", "#242A38")
FIELD_COLOR = ("#E6E9F0", "#232938")
FIELD_HOVER = ("#D9DDE7", "#2D3447")
TEXT_COLOR = ("#151922", "#EEF0F5")
MUTED_TEXT = ("#667085", "#8C95A9")
AMBIENT_LINE = ("#D98A00", "#FFB224")
BRIGHTNESS_LINE = ("#2A6FDB", "#5CA8FF")
GRAPH_BACKGROUND = ("#F4F6FA", "#12161E")
GRAPH_GRID = ("#E1E5EC", "#202635")
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
        return "Pausiert", False
    if status.state == "error":
        return f"{status.message} – neuer Versuch folgt", True
    if status.state == "starting":
        return "Starte …", False
    if not status.exposure_control_available:
        return "Messung ungenau", True
    if not status.reliable:
        return "Messgrenze erreicht", True
    return "Aktiv", False


def _color(pair: tuple[str, str]) -> str:
    return pair[1] if customtkinter.get_appearance_mode() == "Dark" else pair[0]


def _font(size: int, weight: str = "normal") -> customtkinter.CTkFont:
    return customtkinter.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


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

        self.title("AutoBrightness")
        self.geometry("470x800")
        self.minsize(430, 520)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._icon_image = tk.PhotoImage(master=self, data=render_icon(64, png_base64=True))
        self.iconphoto(True, self._icon_image)

        self._build()
        self.after(REFRESH_MS, self._refresh)

    # ----- Aufbau -----

    def _card(self, title: str, trailing: Optional[Callable[[customtkinter.CTkFrame], None]] = None) -> customtkinter.CTkFrame:
        card = customtkinter.CTkFrame(
            self._body, fg_color=CARD_COLOR, corner_radius=14, border_width=1, border_color=CARD_BORDER
        )
        card.pack(fill="x", padx=14, pady=(0, 10))
        header = customtkinter.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(11, 4))
        customtkinter.CTkLabel(
            header, text=title.upper(), text_color=MUTED_TEXT, font=_font(11, "bold")
        ).pack(side="left")
        if trailing is not None:
            trailing(header)
        return card

    def _build(self) -> None:
        data = self._settings.snapshot()

        header = customtkinter.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(14, 10))
        self._logo = customtkinter.CTkImage(render_icon(64), size=(30, 30))
        customtkinter.CTkLabel(header, image=self._logo, text="").pack(side="left")
        customtkinter.CTkLabel(
            header, text="AutoBrightness", text_color=TEXT_COLOR, font=_font(20, "bold")
        ).pack(side="left", padx=(9, 0))
        self._enabled_switch = customtkinter.CTkSwitch(
            header, text="", width=44, progress_color=ACCENT, command=self._toggle_enabled
        )
        self._enabled_switch.pack(side="right")
        if data.enabled:
            self._enabled_switch.select()
        self._status_label = customtkinter.CTkLabel(header, text="", font=_font(12, "bold"))
        self._status_label.pack(side="right", padx=(0, 10))
        self._status_dot = customtkinter.CTkLabel(header, text="●", font=_font(11), text_color=MUTED_TEXT)
        self._status_dot.pack(side="right", padx=(0, 4))

        self._body = customtkinter.CTkScrollableFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True)

        self._build_live_card()
        self._build_calibration_card(data)

        range_card = self._card("Helligkeitsbereich")
        self._add_slider(range_card, "min_brightness_percent", "Minimum", 0, 100, data, lambda value: f"{int(value)} %", 100)
        self._add_slider(range_card, "max_brightness_percent", "Maximum", 0, 100, data, lambda value: f"{int(value)} %", 100)
        self._add_slider(range_card, "brightness_offset_percent", "Versatz", -30, 30, data, lambda value: f"{int(value):+d} %", 60)

        behaviour = self._card("Verhalten")
        self._add_slider(behaviour, "response_time_s", "Trägheit", 0, 30, data, lambda value: f"{value:.0f} s", 30)
        self._add_slider(behaviour, "measure_interval_s", "Messintervall", 0.3, 10, data, lambda value: f"{value:.1f} s", 97)
        self._add_slider(behaviour, "hysteresis_percent", "Mindeständerung", 0, 10, data, lambda value: f"{int(value)} %", 10)

        monitors = [AUTO_MONITOR_LABEL] + display.list_monitors()

        def add_monitor_menu(parent: customtkinter.CTkFrame) -> None:
            menu = customtkinter.CTkOptionMenu(
                parent, values=monitors, command=self._select_monitor, height=26, width=170,
                font=_font(12), dropdown_font=_font(12), corner_radius=8,
                fg_color=FIELD_COLOR, button_color=FIELD_HOVER, button_hover_color=FIELD_HOVER,
                text_color=TEXT_COLOR, dropdown_text_color=TEXT_COLOR,
            )
            menu.set(data.monitor if data.monitor in monitors else AUTO_MONITOR_LABEL)
            menu.pack(side="right")

        screen = self._card("Bildschirm", add_monitor_menu)
        self._add_slider(screen, "night_shift_percent", "Nachtlicht", 0, 100, data, lambda value: f"{int(value)} %", 100)

        self._build_system_row()

        customtkinter.CTkLabel(
            self._body, text=f"Version {__version__}", text_color=MUTED_TEXT, font=_font(11)
        ).pack(pady=(0, 10))

    def _build_live_card(self) -> None:
        live = self._card("Live")
        summary = customtkinter.CTkFrame(live, fg_color="transparent")
        summary.pack(fill="x", padx=16)
        self._brightness_label = customtkinter.CTkLabel(
            summary, text="–", text_color=ACCENT, font=_font(44, "bold")
        )
        self._brightness_label.pack(side="left")
        details = customtkinter.CTkFrame(summary, fg_color="transparent")
        details.pack(side="right")
        self._ambient_label = customtkinter.CTkLabel(
            details, text="", text_color=TEXT_COLOR, font=_font(13, "bold"), anchor="e", justify="right"
        )
        self._ambient_label.pack(anchor="e")
        self._shutter_label = customtkinter.CTkLabel(
            details, text="", text_color=MUTED_TEXT, font=_font(12), anchor="e"
        )
        self._shutter_label.pack(anchor="e")

        scale = customtkinter.CTkFrame(live, fg_color="transparent")
        scale.pack(fill="x", padx=16, pady=(2, 0))
        customtkinter.CTkLabel(scale, text="dunkel", text_color=MUTED_TEXT, font=_font(11)).pack(side="left")
        customtkinter.CTkLabel(scale, text="hell", text_color=MUTED_TEXT, font=_font(11)).pack(side="right")
        self._ambient_bar = customtkinter.CTkProgressBar(
            scale, progress_color=ACCENT, fg_color=FIELD_COLOR, height=6
        )
        self._ambient_bar.set(0)
        self._ambient_bar.pack(fill="x", expand=True, padx=8)

        self._graph = tk.Canvas(live, height=64, highlightthickness=0, bd=0)
        self._graph.pack(fill="x", padx=16, pady=(8, 4))
        legend = customtkinter.CTkFrame(live, fg_color="transparent")
        legend.pack(fill="x", padx=16, pady=(0, 12))
        for text, color in (("Umgebungslicht", AMBIENT_LINE), ("Bildschirm", BRIGHTNESS_LINE)):
            customtkinter.CTkLabel(legend, text="●", text_color=color, font=_font(10)).pack(side="left")
            customtkinter.CTkLabel(legend, text=text, text_color=MUTED_TEXT, font=_font(11)).pack(
                side="left", padx=(3, 12)
            )

    def _build_calibration_card(self, data) -> None:
        card = self._card("Kalibrierung")
        buttons = customtkinter.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(0, 4))
        buttons.columnconfigure((0, 1), weight=1, uniform="calibration")
        for column, (dark, label) in enumerate(((True, "Jetzt = dunkel"), (False, "Jetzt = hell"))):
            button = customtkinter.CTkButton(
                buttons, text=label, height=32, corner_radius=9, font=_font(13, "bold"),
                fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                command=lambda is_dark=dark: self._service.calibrate(is_dark),
            )
            button.grid(row=0, column=column, padx=(0, 4) if column == 0 else (4, 0), sticky="ew")
        self._calibration_label = customtkinter.CTkLabel(
            card, text="", text_color=MUTED_TEXT, font=_font(11)
        )
        self._calibration_label.pack(pady=(0, 10))

    def _build_system_row(self) -> None:
        row = customtkinter.CTkFrame(
            self._body, fg_color=CARD_COLOR, corner_radius=14, border_width=1, border_color=CARD_BORDER
        )
        row.pack(fill="x", padx=14, pady=(0, 8))
        self._autostart_switch = customtkinter.CTkSwitch(
            row, text="Mit Windows starten", font=_font(13), text_color=TEXT_COLOR,
            progress_color=ACCENT, command=self._toggle_autostart,
        )
        self._autostart_switch.pack(side="left", padx=16, pady=11)
        if startup.is_enabled():
            self._autostart_switch.select()
        customtkinter.CTkButton(
            row, text="Beenden", width=84, height=28, corner_radius=8, font=_font(12, "bold"),
            fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR, command=self._on_quit,
        ).pack(side="right", padx=16)

    def _add_slider(self, parent, key, label, minimum, maximum, data, formatter, steps) -> None:
        row = customtkinter.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=1)
        row.columnconfigure(1, weight=1)
        customtkinter.CTkLabel(
            row, text=label, width=118, anchor="w", text_color=TEXT_COLOR, font=_font(13)
        ).grid(row=0, column=0)
        value_label = customtkinter.CTkLabel(
            row, text=formatter(getattr(data, key)), width=52, anchor="e", text_color=MUTED_TEXT, font=_font(12)
        )
        value_label.grid(row=0, column=2)

        def on_change(value: float) -> None:
            value_label.configure(text=formatter(value))
            self._schedule_save(key, value)

        slider = customtkinter.CTkSlider(
            row, from_=minimum, to=maximum, number_of_steps=steps, height=14,
            fg_color=FIELD_COLOR, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, command=on_change,
        )
        slider.set(getattr(data, key))
        slider.grid(row=0, column=1, sticky="ew", padx=8)
        customtkinter.CTkFrame(parent, height=0, fg_color="transparent").pack(pady=(0, 3))

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
        paused = status.state == "disabled"
        dot_color = DANGER if warning else (MUTED_TEXT if paused else SUCCESS)
        self._status_label.configure(text=text, text_color=dot_color)
        self._status_dot.configure(text_color=dot_color)
        self.sync_enabled_switch()

        if status.exposure_value is None:
            self._brightness_label.configure(text="–")
            self._ambient_label.configure(text="")
            self._shutter_label.configure(text="")
            self._ambient_bar.set(0)
        else:
            self._brightness_label.configure(text=f"{status.applied_percent} %")
            self._ambient_label.configure(text=f"Umgebungslicht {status.exposure_value:.1f} EV")
            self._shutter_label.configure(text=f"Belichtung {format_shutter(status.exposure_log2_seconds)}")
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
