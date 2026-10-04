import os
import sys
import time
import threading
import json
import subprocess
from typing import Optional

import cv2
import numpy as np
import ctypes

try:
    import screen_brightness_control as sbc
except Exception:
    sbc = None

try:
    import pystray
    from pystray import MenuItem as Item
except Exception:
    pystray = None
    Item = None

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None
    ttk = None

# -------- Config --------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULTS = {
    "camera_index": 0,
    "capture_interval_s": 0.5,
    "smoothing_alpha": 0.25,
    "min_luma": 30,
    "max_luma": 200,
    "min_brightness": 20,
    "max_brightness": 100,
    "hysteresis": 3,
    "monitor": None,
    "night_shift": 0,
    "camera_enabled": True,
    "enabled": True,
}

CLICK_MONITOR_DDC = os.path.join(os.path.dirname(__file__), "ClickMonitorDDC_7_2.exe")


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.data = DEFAULTS.copy()
        self.load()

    def load(self) -> None:
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            with self._lock:
                for k in self.data:
                    if k in raw:
                        self.data[k] = raw[k]
        except Exception:
            # If config is broken, keep defaults
            pass

    def save(self) -> None:
        with self._lock:
            data = dict(self.data)
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get(self, key: str):
        with self._lock:
            return self.data[key]

    def set(self, key: str, value) -> None:
        with self._lock:
            self.data[key] = value
        self.save()


settings = Settings()
status_lock = threading.Lock()
status = {
    "luma": None,
    "target": None,
    "set": None,
    "night_shift": 0,
    "night_shift_ok": None,
    "camera_enabled": True,
}
tray_icon = None


def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("Webcam not accessible")
    return cap


def get_webcam_luma(cap: cv2.VideoCapture) -> Optional[float]:
    ok, frame = cap.read()
    if not ok:
        return None
    frame = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    return float(np.mean(v))


def luma_to_brightness(luma: float) -> int:
    min_luma = float(settings.get("min_luma"))
    max_luma = float(settings.get("max_luma"))
    min_b = float(settings.get("min_brightness"))
    max_b = float(settings.get("max_brightness"))

    luma = max(min_luma, min(luma, max_luma))
    ratio = (luma - min_luma) / (max_luma - min_luma)
    brightness = min_b + ratio * (max_b - min_b)
    return int(round(brightness))


def set_brightness(percent: int) -> None:
    percent = int(max(0, min(100, percent)))

    if sbc is not None:
        monitor = settings.get("monitor")
        try:
            if monitor:
                sbc.set_brightness(percent, display=monitor)
            else:
                sbc.set_brightness(percent)
        except Exception:
            sbc.set_brightness(percent)
        return

    if os.path.exists(CLICK_MONITOR_DDC):
        subprocess.run([CLICK_MONITOR_DDC, f"d{percent}"], check=False)
        return

    raise RuntimeError("No brightness backend available. Install screen_brightness_control or use ClickMonitorDDC.")


def apply_night_shift(percent: int) -> bool:
    # Simple blue-light filter using gamma ramp on Windows.
    # percent: 0..100 (0 = off, 100 = strongest)
    percent = max(0, min(100, int(percent)))
    strength = percent / 100.0

    # Reduce blue channel and slightly reduce green to make the screen warmer.
    blue_scale = 1.0 - 0.45 * strength
    green_scale = 1.0 - 0.20 * strength
    red_scale = 1.0

    ramp = (ctypes.c_ushort * (3 * 256))()
    for i in range(256):
        val = i * 256
        ramp[i] = int(min(65535, val * red_scale))
        ramp[i + 256] = int(min(65535, val * green_scale))
        ramp[i + 512] = int(min(65535, val * blue_scale))

    hdc = ctypes.windll.user32.GetDC(0)
    ok = bool(ctypes.windll.gdi32.SetDeviceGammaRamp(hdc, ramp))
    ctypes.windll.user32.ReleaseDC(0, hdc)
    return ok


def worker_loop(stop_event: threading.Event) -> None:
    last_set = None
    smoothed = None
    last_night_shift = None
    cap = None

    try:
        while not stop_event.is_set():
            if not settings.get("enabled"):
                time.sleep(0.2)
                continue

            if not settings.get("camera_enabled"):
                if cap is not None:
                    cap.release()
                    cap = None
                with status_lock:
                    status["camera_enabled"] = False
                    status["luma"] = None
                    status["target"] = None
                time.sleep(0.2)
                continue

            if cap is None:
                try:
                    cap = open_camera(int(settings.get("camera_index")))
                except Exception:
                    time.sleep(0.5)
                    continue

            luma = get_webcam_luma(cap)
            if luma is None:
                time.sleep(float(settings.get("capture_interval_s")))
                continue

            target = luma_to_brightness(luma)
            with status_lock:
                status["luma"] = luma
                status["target"] = target
                status["camera_enabled"] = True

            alpha = float(settings.get("smoothing_alpha"))
            if smoothed is None:
                smoothed = float(target)
            else:
                smoothed = alpha * target + (1 - alpha) * smoothed

            candidate = int(round(smoothed))
            hysteresis = int(settings.get("hysteresis"))
            if last_set is None or abs(candidate - last_set) >= hysteresis:
                set_brightness(candidate)
                last_set = candidate
                with status_lock:
                    status["set"] = candidate

            night_shift = int(settings.get("night_shift"))
            if last_night_shift is None or night_shift != last_night_shift:
                ok = apply_night_shift(night_shift)
                last_night_shift = night_shift
                with status_lock:
                    status["night_shift"] = night_shift
                    status["night_shift_ok"] = ok

            time.sleep(float(settings.get("capture_interval_s")))
    finally:
        if cap is not None:
            cap.release()


class SettingsWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AutoBrightness Settings")
        self.root.resizable(False, False)

        self._style = ttk.Style()
        try:
            self._style.theme_use("vista")
        except Exception:
            pass
        self._style.configure("Title.TLabel", font=("Segoe UI", 11, "bold"))
        self._style.configure("Status.TLabel", font=("Segoe UI", 10))

        self.vars = {
            "smoothing_alpha": tk.DoubleVar(value=settings.get("smoothing_alpha")),
            "capture_interval_s": tk.DoubleVar(value=settings.get("capture_interval_s")),
            "hysteresis": tk.IntVar(value=settings.get("hysteresis")),
            "min_luma": tk.IntVar(value=settings.get("min_luma")),
            "max_luma": tk.IntVar(value=settings.get("max_luma")),
            "min_brightness": tk.IntVar(value=settings.get("min_brightness")),
            "max_brightness": tk.IntVar(value=settings.get("max_brightness")),
            "night_shift": tk.IntVar(value=settings.get("night_shift")),
            "camera_enabled": tk.BooleanVar(value=settings.get("camera_enabled")),
        }

        self._build()
        self._attach_traces()
        self._start_status_updates()

    def _build(self):
        pad = {"padx": 10, "pady": 6}

        header = ttk.Label(self.root, text="AutoBrightness", style="Title.TLabel")
        header.grid(row=0, column=0, columnspan=3, sticky="w", **pad)

        status_frame = ttk.LabelFrame(self.root, text="Live Status")
        status_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        self._status_label = ttk.Label(status_frame, text="Luma: --   Target: --   Set: --", style="Status.TLabel")
        self._status_label.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        cam_check = ttk.Checkbutton(
            status_frame,
            text="Use camera (turns on camera LED)",
            variable=self.vars["camera_enabled"],
        )
        cam_check.grid(row=1, column=0, sticky="w", padx=8, pady=2)

        sens_frame = ttk.LabelFrame(self.root, text="Sensitivity")
        sens_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        self._add_slider(
            sens_frame,
            0,
            "Smoothing",
            self.vars["smoothing_alpha"],
            0.05,
            0.8,
            fmt=lambda v: f"{float(v):.2f}",
        )
        self._add_slider(
            sens_frame,
            1,
            "Capture Interval (s)",
            self.vars["capture_interval_s"],
            0.2,
            2.0,
            fmt=lambda v: f"{float(v):.1f}",
        )
        self._add_slider(
            sens_frame,
            2,
            "Hysteresis (%)",
            self.vars["hysteresis"],
            1,
            10,
            fmt=lambda v: f"{int(float(v))}",
        )

        map_frame = ttk.LabelFrame(self.root, text="Luma -> Brightness Mapping")
        map_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        self._add_slider(
            map_frame,
            0,
            "Min Luma",
            self.vars["min_luma"],
            0,
            100,
            fmt=lambda v: f"{int(float(v))}",
        )
        self._add_slider(
            map_frame,
            1,
            "Max Luma",
            self.vars["max_luma"],
            120,
            255,
            fmt=lambda v: f"{int(float(v))}",
        )
        self._add_slider(
            map_frame,
            2,
            "Min Brightness (%)",
            self.vars["min_brightness"],
            0,
            60,
            fmt=lambda v: f"{int(float(v))}%",
        )
        self._add_slider(
            map_frame,
            3,
            "Max Brightness (%)",
            self.vars["max_brightness"],
            60,
            100,
            fmt=lambda v: f"{int(float(v))}%",
        )

        night_frame = ttk.LabelFrame(self.root, text="Night Shift (Blue Light Filter)")
        night_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=6)
        self._add_slider(
            night_frame,
            0,
            "Warmth",
            self.vars["night_shift"],
            0,
            100,
            fmt=lambda v: f"{int(float(v))}%",
        )

        for frame in (sens_frame, map_frame):
            frame.columnconfigure(1, weight=1)
        night_frame.columnconfigure(1, weight=1)

        self.root.columnconfigure(1, weight=1)

    def _add_slider(self, parent, row, label, var, from_, to, fmt):
        pad = {"padx": 8, "pady": 4}
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **pad)
        scale = ttk.Scale(parent, from_=from_, to=to, variable=var, orient="horizontal")
        scale.grid(row=row, column=1, sticky="ew", **pad)

        value_label = ttk.Label(parent, text=fmt(var.get()))
        value_label.grid(row=row, column=2, sticky="e", **pad)

        def on_change(*_):
            value_label.configure(text=fmt(var.get()))

        var.trace_add("write", on_change)

    def _attach_traces(self):
        def on_change(*_):
            self._save()

        for var in self.vars.values():
            var.trace_add("write", on_change)

    def _save(self):
        for key, var in self.vars.items():
            settings.set(key, var.get())

    def _start_status_updates(self):
        def tick():
            with status_lock:
                luma = status["luma"]
                target = status["target"]
                current = status["set"]
            if luma is None:
                text = "Luma: --   Target: --   Set: --   Night Shift: --"
            else:
                ok = status.get("night_shift_ok", None)
                ok_text = "OK" if ok else ("FAIL" if ok is False else "--")
                text = (
                    f"Luma: {int(luma)}   Target: {int(target)}%   "
                    f"Set: {int(current) if current is not None else '--'}%   "
                    f"Night Shift: {int(status.get('night_shift', 0))}% ({ok_text})"
                )
            self._status_label.configure(text=text)
            self.root.after(500, tick)

        tick()


def open_settings_window() -> None:
    if tk is None:
        return
    root = tk.Tk()
    SettingsWindow(root)
    root.mainloop()


def show_settings(icon, item):
    t = threading.Thread(target=open_settings_window, daemon=True)
    t.start()


def toggle_enabled(icon, item):
    settings.set("enabled", not settings.get("enabled"))
    icon.update_menu()


def quit_app(icon, item):
    icon.stop()


def _status_line() -> str:
    with status_lock:
        luma = status["luma"]
        target = status["target"]
        current = status["set"]
    if luma is None:
        return "Luma: --   Target: --   Set: --   Night Shift: --"
    ok = status.get("night_shift_ok", None)
    ok_text = "OK" if ok else ("FAIL" if ok is False else "--")
    return (
        f"Luma: {int(luma)}   Target: {int(target)}%   "
        f"Set: {int(current) if current is not None else '--'}%   "
        f"Night Shift: {int(status.get('night_shift', 0))}% ({ok_text})"
    )


def _monitors_menu():
    if sbc is None:
        return (Item("ClickMonitorDDC", None, enabled=False),)

    monitors = []
    try:
        monitors = sbc.list_monitors()
    except Exception:
        monitors = []

    if not monitors:
        return (Item("No monitors found", None, enabled=False),)

    current = settings.get("monitor")

    def make_item(label, value):
        def action(icon, item):
            _set_monitor(value)

        return Item(
            label,
            action,
            checked=lambda item: settings.get("monitor") == value,
        )

    items = [make_item("Auto (default)", None)]
    items.extend(make_item(name, name) for name in monitors)
    return tuple(items)


def _set_monitor(name: str):
    settings.set("monitor", name)
    if tray_icon is not None:
        tray_icon.update_menu()


def run_tray(stop_event: threading.Event) -> None:
    if pystray is None:
        return

    menu = pystray.Menu(
        Item(lambda item: _status_line(), None, enabled=False),
        Item("Settings", show_settings),
        Item("Monitor", pystray.Menu(_monitors_menu)),
        Item("Enabled", toggle_enabled, checked=lambda item: settings.get("enabled")),
        Item("Quit", quit_app),
    )

    # Simple white sun icon (no external file needed)
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(image)
    d.ellipse((16, 16, 48, 48), fill="white")

    global tray_icon
    tray_icon = pystray.Icon("AutoBrightness", image, "AutoBrightness", menu)
    tray_icon.run()
    stop_event.set()


def main() -> int:
    stop_event = threading.Event()

    worker = threading.Thread(target=worker_loop, args=(stop_event,), daemon=True)
    worker.start()

    tray = threading.Thread(target=run_tray, args=(stop_event,), daemon=True)
    tray.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
