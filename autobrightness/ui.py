"""Einstellungsfenster (customtkinter) mit Live-Anzeige."""

from __future__ import annotations

import ctypes
import math
import queue
import tempfile
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

import customtkinter
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from . import __version__, display, startup
from . import mapping
from .chart import Painter
from .config import EXPOSURE_VALUE_RANGE, MIN_CALIBRATION_POINTS, MIN_POINT_DISTANCE, Settings
from .icon import apply_window_icon, write_ico
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
MAX_INTERVAL_S = 86400
MIN_GRAPH_SAMPLES = 60
CURVE_MARGIN_LEFT, CURVE_MARGIN_TOP, CURVE_MARGIN_RIGHT, CURVE_MARGIN_BOTTOM = 12, 10, 40, 22
POINT_GRAB_RADIUS = 10
RESET_CONFIRM_MS = 3000
VISIBLE_POLL_MS = 30
HIDDEN_POLL_MS = 1000
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
    if status.state == "busy":
        users = status.message if len(status.message) <= 26 else status.message[:25] + "…"
        return (f"Pausiert · {users}" if users else "Kamera belegt"), False
    if status.state == "error":
        return status.message, True
    if status.state == "starting":
        return "Starte …", False
    if not status.exposure_control_available:
        return "Messung ungenau", True
    if not status.reliable:
        return "Messgrenze erreicht", True
    return "Aktiv", False


def _curve_plot_area(width: int, height: int) -> tuple[int, int, int, int]:
    """(links, oben, rechts, unten) der Zeichenfläche des Kurvendiagramms ohne Achsenbeschriftung."""
    return CURVE_MARGIN_LEFT, CURVE_MARGIN_TOP, width - CURVE_MARGIN_RIGHT, height - CURVE_MARGIN_BOTTOM


def _color(pair: tuple[str, str]) -> str:
    return pair[1] if customtkinter.get_appearance_mode() == "Dark" else pair[0]


def _format_duration(seconds: float) -> str:
    if seconds < 120:
        return f"{seconds:.0f} s"
    if seconds < 7200:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h".replace(".", ",")


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
        self.geometry("470x650")
        self.minsize(430, 360)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        # Ein eigenes Fenstersymbol verhindert, dass CustomTkinter sein blaues Standardsymbol setzt.
        with tempfile.TemporaryDirectory() as folder:
            icon_path = Path(folder) / "AutoBrightness.ico"
            write_ico(icon_path)
            self.iconbitmap(str(icon_path))
            self.update_idletasks()
            apply_window_icon(ctypes.windll.user32.GetParent(self.winfo_id()), icon_path)

        self._slider_refreshers: list[Callable] = []
        self._reset_confirm_job = None
        self._build()
        self.after(REFRESH_MS, self._refresh)

    # ----- Aufbau -----

    def _card(self, title: Optional[str], trailing: Optional[Callable[[customtkinter.CTkFrame], None]] = None) -> customtkinter.CTkFrame:
        card = customtkinter.CTkFrame(
            self._body, fg_color=CARD_COLOR, corner_radius=14, border_width=1, border_color=CARD_BORDER
        )
        card.pack(fill="x", padx=14, pady=(0, 10))
        if title is None:
            customtkinter.CTkFrame(card, height=0, fg_color="transparent").pack(pady=(7, 0))
            return card
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
        self._add_slider(range_card, "brightness_offset_percent", "Versatz", -100, 100, data, lambda value: f"{int(value):+d} %", 200)

        behaviour = self._card("Verhalten")
        self._add_slider(behaviour, "response_time_s", "Trägheit", 0, MAX_INTERVAL_S, data, _format_duration, 300, logarithmic=True)
        self._add_slider(behaviour, "measure_interval_s", "Messintervall", 2, MAX_INTERVAL_S, data, _format_duration, 300, logarithmic=True)
        self._add_slider(behaviour, "hysteresis_percent", "Mindeständerung", 0, 50, data, lambda value: f"{int(value)} %", 50)

        monitors = [AUTO_MONITOR_LABEL] + display.list_monitors()

        def add_monitor_menu(parent: customtkinter.CTkFrame) -> None:
            menu = customtkinter.CTkOptionMenu(
                parent, values=monitors, command=self._select_monitor, height=26, width=170,
                font=_font(12), dropdown_font=_font(12), corner_radius=8,
                fg_color=FIELD_COLOR, button_color=FIELD_HOVER, button_hover_color=FIELD_HOVER,
                text_color=TEXT_COLOR, dropdown_text_color=TEXT_COLOR,
            )
            menu.set(data.monitor if data.monitor in monitors else AUTO_MONITOR_LABEL)
            self._slider_refreshers.append(
                lambda current: menu.set(current.monitor if current.monitor in monitors else AUTO_MONITOR_LABEL)
            )
            menu.pack(side="right")

        screen = self._card("Bildschirm", add_monitor_menu)
        self._add_slider(screen, "night_shift_percent", "Nachtlicht", 0, 100, data, lambda value: f"{int(value)} %", 100)

        self._build_system_row()

        customtkinter.CTkLabel(
            self._body, text=f"Version {__version__}", text_color=MUTED_TEXT, font=_font(11)
        ).pack(pady=(0, 10))

    def _build_live_card(self) -> None:
        live = self._card(None)
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
        self._graph_key = None
        legend = customtkinter.CTkFrame(live, fg_color="transparent")
        legend.pack(fill="x", padx=16, pady=(0, 12))
        for text, color in (("Umgebungslicht", AMBIENT_LINE), ("Bildschirm", BRIGHTNESS_LINE)):
            customtkinter.CTkLabel(legend, text="●", text_color=color, font=_font(10)).pack(side="left")
            customtkinter.CTkLabel(legend, text=text, text_color=MUTED_TEXT, font=_font(11)).pack(
                side="left", padx=(3, 12)
            )

    def _build_calibration_card(self, data) -> None:
        card = self._card("Kalibrierung")
        self._curve = tk.Canvas(card, height=180, highlightthickness=0, bd=0)
        self._curve.pack(fill="x", padx=16, pady=(0, 6))
        self._dragged_point: Optional[int] = None
        self._curve_key = None
        self._curve.bind("<Button-1>", self._on_curve_press)
        self._curve.bind("<B1-Motion>", self._on_curve_drag)
        self._curve.bind("<ButtonRelease-1>", lambda event: setattr(self, "_dragged_point", None))
        self._curve.configure(cursor="crosshair")

        chooser = customtkinter.CTkFrame(card, fg_color="transparent")
        chooser.pack(fill="x", padx=16, pady=(0, 4))
        self._point_percent = 50.0
        self._point_percent_touched = False
        self._point_percent_label = customtkinter.CTkLabel(
            chooser, text="", width=44, text_color=TEXT_COLOR, font=_font(13, "bold"), anchor="e"
        )
        self._point_percent_label.pack(side="right")
        self._point_slider = customtkinter.CTkSlider(
            chooser, from_=0, to=100, number_of_steps=100, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER, command=self._on_point_slider,
        )
        self._point_slider.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._point_slider.set(self._point_percent)
        self._point_percent_label.configure(text=f"{int(self._point_percent)} %")

        customtkinter.CTkButton(
            card, text="Jetzt mit dieser Helligkeit als Punkt festlegen", height=32, corner_radius=9,
            font=_font(13, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            command=lambda: self._service.add_calibration_point(self._point_percent),
        ).pack(fill="x", padx=16, pady=(2, 6))
        customtkinter.CTkLabel(
            card, text="Passende Helligkeit für das jetzige Licht einstellen und festlegen – beliebig oft "
            "bei verschiedenem Licht. Punkte lassen sich in der Kurve ziehen; ein Klick daneben setzt einen neuen.",
            text_color=MUTED_TEXT, font=_font(11), wraplength=380, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 6))
        self._points_toggle = customtkinter.CTkButton(
            card, text="", height=26, corner_radius=8, font=_font(12), anchor="w",
            fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR, command=self._toggle_point_list,
        )
        self._points_toggle.pack(fill="x", padx=16, pady=(0, 10))
        self._points_frame = customtkinter.CTkFrame(card, fg_color="transparent")
        self._points_expanded = False
        self._listed_points: Optional[list] = None
        self._point_count = 0

    def _toggle_point_list(self) -> None:
        self._points_expanded = not self._points_expanded
        if self._points_expanded:
            self._points_frame.pack(fill="x", padx=16, pady=(0, 10))
        else:
            self._points_frame.pack_forget()
        self._update_point_toggle()

    def _update_point_toggle(self) -> None:
        arrow = "▾" if self._points_expanded else "▸"
        self._points_toggle.configure(text=f"{arrow}  Kalibrierpunkte ({self._point_count})")

    def _on_point_slider(self, value: float) -> None:
        self._point_percent = float(round(value))
        self._point_percent_touched = True
        self._point_percent_label.configure(text=f"{int(self._point_percent)} %")

    def _curve_bounds(self, data) -> tuple[float, float]:
        values = [point[0] for point in data.calibration_points]
        current = self._service.status.exposure_value
        if current is not None:
            values.append(current)
        return min(values) - 0.5, max(values) + 0.5

    def _curve_geometry(self, data) -> tuple[float, float, int, int]:
        low, high = self._curve_bounds(data)
        return low, high, max(self._curve.winfo_width(), 50), max(self._curve.winfo_height(), 50)

    def _curve_position(self, event_x: int, event_y: int, data) -> tuple[float, float]:
        """(Blendenstufe, Prozent) zu einer Position auf der Zeichenfläche."""
        low, high, width, height = self._curve_geometry(data)
        left, top, right, bottom = _curve_plot_area(width, height)
        exposure_value = low + (event_x - left) / (right - left) * (high - low)
        percent = 100 * (bottom - event_y) / (bottom - top)
        return exposure_value, max(0.0, min(100.0, percent))

    def _on_curve_press(self, event) -> None:
        """Greift einen nahen Punkt zum Verschieben; sonst wird an der Stelle ein neuer Punkt gesetzt."""
        data = self._settings.snapshot()
        low, high, width, height = self._curve_geometry(data)
        self._dragged_point = None
        left, top, right, bottom = _curve_plot_area(width, height)
        nearest = None
        for index, (exposure_value, percent) in enumerate(data.calibration_points):
            x = left + (exposure_value - low) / (high - low) * (right - left)
            y = bottom - percent / 100 * (bottom - top)
            distance = math.hypot(event.x - x, event.y - y)
            if distance <= POINT_GRAB_RADIUS and (nearest is None or distance < nearest[0]):
                nearest = (distance, index)
        if nearest is not None:
            self._dragged_point = nearest[1]
            return
        exposure_value, percent = self._curve_position(event.x, event.y, data)
        points = [point for point in data.calibration_points if abs(point[0] - exposure_value) >= MIN_POINT_DISTANCE]
        self._settings.update(calibration_points=points + [[exposure_value, percent]])
        self._draw_curve(self._settings.snapshot())

    def _on_curve_drag(self, event) -> None:
        """Verschiebt den gegriffenen Punkt, ohne die Reihenfolge der Punkte zu verändern."""
        index = self._dragged_point
        if index is None:
            return
        points = self._settings.snapshot().calibration_points
        data = self._settings.snapshot()
        exposure_value, percent = self._curve_position(event.x, event.y, data)
        lower = points[index - 1][0] + MIN_POINT_DISTANCE if index > 0 else EXPOSURE_VALUE_RANGE[0]
        upper = points[index + 1][0] - MIN_POINT_DISTANCE if index < len(points) - 1 else EXPOSURE_VALUE_RANGE[1]
        points[index] = [max(lower, min(upper, exposure_value)), percent]
        self._settings.update(calibration_points=points)
        self._draw_curve(self._settings.snapshot())

    def _update_point_list(self, points) -> None:
        if points == self._listed_points:
            return
        self._listed_points = [list(point) for point in points]
        self._point_count = len(points)
        self._update_point_toggle()
        for child in self._points_frame.winfo_children():
            child.destroy()
        removable = len(points) > MIN_CALIBRATION_POINTS
        for index, (exposure_value, percent) in enumerate(points):
            row = customtkinter.CTkFrame(self._points_frame, fg_color="transparent")
            row.pack(fill="x")
            customtkinter.CTkLabel(
                row, text=f"{exposure_value:.1f} EV   →   {percent:.0f} %", text_color=TEXT_COLOR, font=_font(12)
            ).pack(side="left")
            customtkinter.CTkButton(
                row, text="✕", width=26, height=22, corner_radius=6, font=_font(11),
                fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR,
                state="normal" if removable else "disabled",
                command=lambda position=index: self._service.remove_calibration_point(position),
            ).pack(side="right", pady=1)

    def _draw_curve(self, data) -> None:
        low, high, width, height = self._curve_geometry(data)
        current = self._service.status.exposure_value
        key = (width, height, low, high, current, data.min_brightness_percent, data.max_brightness_percent,
               data.brightness_offset_percent, tuple(map(tuple, data.calibration_points)), _color(GRAPH_BACKGROUND))
        if key == self._curve_key:
            return
        self._curve_key = key
        painter = Painter(width, height, _color(GRAPH_BACKGROUND))

        left, top, right, bottom = _curve_plot_area(width, height)

        def x_of(exposure_value: float) -> float:
            return left + (exposure_value - low) / (high - low) * (right - left)

        def y_of(percent: float) -> float:
            return bottom - percent / 100 * (bottom - top)

        for percent in (0, 25, 50, 75, 100):
            painter.line([left, y_of(percent), right, y_of(percent)], _color(GRAPH_GRID))
            painter.text(right + 7, y_of(percent), f"{percent} %", _color(MUTED_TEXT), 10, anchor="lm")
        tick = math.ceil(low)
        while tick <= high:
            painter.line([x_of(tick), top, x_of(tick), bottom], _color(GRAPH_GRID))
            painter.text(x_of(tick), bottom + 5, f"{tick}", _color(MUTED_TEXT), 10, anchor="ma")
            tick += max(1, math.ceil((high - low) / 8))
        painter.text(right + 7, bottom + 5, "EV", _color(MUTED_TEXT), 10, anchor="la")

        samples = 160
        curve = []
        for index in range(samples + 1):
            exposure_value = low + (high - low) * index / samples
            curve += [x_of(exposure_value), y_of(mapping.target_brightness(exposure_value, data))]
        painter.line(curve, _color(BRIGHTNESS_LINE), 2)

        if current is not None:
            x, y = x_of(current), y_of(mapping.target_brightness(current, data))
            painter.dashed_line((x, y_of(100)), (x, y_of(0)), _color(AMBIENT_LINE), 1, 3)
            painter.circle(x, y, 5, fill=_color(AMBIENT_LINE))

        for exposure_value, percent in data.calibration_points:
            painter.circle(x_of(exposure_value), y_of(percent), 4.5, fill=_color(CARD_COLOR), outline=_color(BRIGHTNESS_LINE), width=2)
        painter.show(self._curve)

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
        self._reset_button = customtkinter.CTkButton(
            row, text="Zurücksetzen", width=100, height=28, corner_radius=8, font=_font(12, "bold"),
            fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR, command=self._reset_settings,
        )
        self._reset_button.pack(side="right", padx=(0, 16))
        customtkinter.CTkButton(
            row, text="Beenden", width=84, height=28, corner_radius=8, font=_font(12, "bold"),
            fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR, command=self._on_quit,
        ).pack(side="right")

    def _add_slider(self, parent, key, label, minimum, maximum, data, formatter, steps, logarithmic=False) -> None:
        """Bei logarithmic=True läuft der Regler exponentiell, damit kleine und große Werte fein einstellbar sind."""
        if logarithmic:
            offset = 1.0 - minimum
            to_value = lambda position: (minimum + offset) ** (1 - position) * (maximum + offset) ** position - offset
            to_position = lambda value: math.log((value + offset) / (minimum + offset)) / math.log((maximum + offset) / (minimum + offset))
        else:
            to_value = lambda position: position
            to_position = lambda value: value
        slider_minimum, slider_maximum = (0.0, 1.0) if logarithmic else (minimum, maximum)

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

        def on_change(position: float) -> None:
            value = to_value(position)
            value_label.configure(text=formatter(value))
            self._schedule_save(key, value)

        slider = customtkinter.CTkSlider(
            row, from_=slider_minimum, to=slider_maximum, number_of_steps=steps, height=14,
            fg_color=FIELD_COLOR, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, command=on_change,
        )
        slider.set(to_position(getattr(data, key)))
        slider.grid(row=0, column=1, sticky="ew", padx=8)

        def refresh(current) -> None:
            slider.set(to_position(getattr(current, key)))
            value_label.configure(text=formatter(getattr(current, key)))

        self._slider_refreshers.append(refresh)
        customtkinter.CTkFrame(parent, height=0, fg_color="transparent").pack(pady=(0, 3))

    def _reset_settings(self) -> None:
        """Erster Klick fordert Bestätigung an, ein zweiter innerhalb weniger Sekunden setzt zurück."""
        if self._reset_confirm_job is None:
            self._reset_button.configure(text="Sicher?", fg_color=DANGER, hover_color=DANGER, text_color="#FFFFFF")
            self._reset_confirm_job = self.after(RESET_CONFIRM_MS, self._cancel_reset_confirmation)
            return
        self._cancel_reset_confirmation()
        for job in self._pending_saves.values():
            self.after_cancel(job)
        self._pending_saves.clear()
        self._settings.reset()
        data = self._settings.snapshot()
        for refresh in self._slider_refreshers:
            refresh(data)
        self._point_percent_touched = False

    def _cancel_reset_confirmation(self) -> None:
        if self._reset_confirm_job is not None:
            self.after_cancel(self._reset_confirm_job)
            self._reset_confirm_job = None
        self._reset_button.configure(text="Zurücksetzen", fg_color=FIELD_COLOR, hover_color=FIELD_HOVER, text_color=TEXT_COLOR)

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
        self._set_polling_interval(VISIBLE_POLL_MS)
        AppearanceModeTracker.init_appearance_mode()
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        self.withdraw()
        self._set_polling_interval(HIDDEN_POLL_MS)

    @staticmethod
    def _set_polling_interval(interval_ms: int) -> None:
        """Die Hell/Dunkel- und Skalierungsabfragen von CustomTkinter sind nur bei sichtbarem Fenster nötig."""
        AppearanceModeTracker.update_loop_interval = interval_ms
        ScalingTracker.update_loop_interval = max(interval_ms, 100)

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
            dark, bright = data.calibration_points[0][0], data.calibration_points[-1][0]
            self._ambient_bar.set(max(0.0, min(1.0, (status.exposure_value - dark) / (bright - dark))))
        if not self._point_percent_touched and status.applied_percent is not None:
            self._point_slider.set(status.applied_percent)
            self._point_percent = float(status.applied_percent)
            self._point_percent_label.configure(text=f"{status.applied_percent} %")
        self._update_point_list(data.calibration_points)
        self._draw_curve(data)
        self._draw_graph(data)

    def _draw_graph(self, data) -> None:
        width, height = max(self._graph.winfo_width(), 50), max(self._graph.winfo_height(), 50)
        history = list(self._service.history)
        key = (width, height, history[0][0] if history else None, history[-1][0] if history else None,
               data.calibration_points[0][0], data.calibration_points[-1][0], _color(GRAPH_BACKGROUND))
        if key == self._graph_key:
            return
        self._graph_key = key
        painter = Painter(width, height, _color(GRAPH_BACKGROUND))
        for fraction in (0.25, 0.5, 0.75):
            painter.line([0, height * fraction, width, height * fraction], _color(GRAPH_GRID))
        if len(history) >= 2:
            low = min(data.calibration_points[0][0], min(entry[1] for entry in history)) - 0.5
            high = max(data.calibration_points[-1][0], max(entry[1] for entry in history)) + 0.5
            step = width / (max(len(history), MIN_GRAPH_SAMPLES) - 1)

            def line(values: list[float], color: str) -> None:
                points = []
                for index, value in enumerate(values):
                    points += [index * step, height - 6 - value * (height - 12)]
                painter.line(points, color, 2)

            line([(entry[1] - low) / (high - low) for entry in history], _color(AMBIENT_LINE))
            line([entry[2] / 100 for entry in history], _color(BRIGHTNESS_LINE))
        painter.show(self._graph)
