"""Programm-Symbol: Sonne auf dunkler Kachel, zur Laufzeit gezeichnet (keine Bilddateien nötig).

Dieselbe Zeichnung dient für Fenster, Infobereich und die EXE-Datei (write_ico).
"""

from __future__ import annotations

import base64
import io
import math
import ctypes
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SM_CXICON = 11
SM_CXSMICON = 49
WM_SETICON = 0x0080
ICON_SMALL, ICON_BIG = 0, 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
TILE_TOP = (36, 48, 78)
TILE_BOTTOM = (13, 19, 36)
SUN_LIGHT = (255, 222, 128)
SUN_DARK = (245, 158, 28)
SMALL_ICON_LIMIT = 32


def _vertical_gradient(canvas: int, top, bottom) -> Image.Image:
    ramp = np.linspace(0.0, 1.0, canvas)[:, None, None]
    pixels = np.array(top, dtype=float) * (1 - ramp) + np.array(bottom, dtype=float) * ramp
    return Image.fromarray(np.repeat(pixels, canvas, axis=1).astype(np.uint8), "RGB")


def _sun_mask(canvas: int, small: bool) -> Image.Image:
    """Scheibe mit acht Strahlen (abwechselnd lang und kurz); bei kleinen Größen etwas kräftiger gezeichnet."""
    mask = Image.new("L", (canvas, canvas), 0)
    draw = ImageDraw.Draw(mask)
    center = canvas / 2
    disc_radius = canvas * (0.195 if small else 0.185)
    width = canvas * (0.075 if small else 0.062)
    for index in range(8):
        long_ray = index % 2 == 0
        angle = index * math.pi / 4
        inner = canvas * 0.29
        outer = canvas * (0.405 if long_ray else 0.36)
        start = (center + inner * math.cos(angle), center + inner * math.sin(angle))
        end = (center + outer * math.cos(angle), center + outer * math.sin(angle))
        draw.line((*start, *end), fill=255, width=int(width))
        for x, y in (start, end):
            draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=255)
    draw.ellipse((center - disc_radius, center - disc_radius, center + disc_radius, center + disc_radius), fill=255)
    return mask


def _render_canvas(canvas: int, small: bool) -> Image.Image:
    corner = canvas * 0.225
    tile_mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(tile_mask).rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=corner, fill=255)

    image = _vertical_gradient(canvas, TILE_TOP, TILE_BOTTOM).convert("RGBA")
    image.putalpha(tile_mask)

    sun_mask = _sun_mask(canvas, small)
    if not small:
        glow = Image.new("RGBA", (canvas, canvas), SUN_DARK + (0,))
        glow.putalpha(sun_mask.filter(ImageFilter.GaussianBlur(canvas * 0.035)).point(lambda value: int(value * 0.55)))
        image = Image.alpha_composite(image, glow)

    sun = _vertical_gradient(canvas, SUN_LIGHT, SUN_DARK).convert("RGBA")
    sun.putalpha(sun_mask)
    image = Image.alpha_composite(image, sun)

    if not small:
        rim = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle(
            (0, 0, canvas - 1, canvas - 1), radius=corner, outline=(255, 255, 255, 38), width=max(1, canvas // 128)
        )
        image = Image.alpha_composite(image, rim)
    return image


def render_icon(size: int = 64, png_base64: bool = False):
    """PIL-Bild des Symbols; mit png_base64=True als Base64-PNG-Text (für tkinter.PhotoImage)."""
    supersampling = 8 if size <= SMALL_ICON_LIMIT else 4
    image = _render_canvas(size * supersampling, small=size <= SMALL_ICON_LIMIT)
    image = image.resize((size, size), Image.LANCZOS)
    if not png_base64:
        return image
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def write_ico(path: Path) -> None:
    """Schreibt eine .ico mit jeder Größe einzeln gezeichnet (scharf auch bei 16 px)."""
    entries = []
    for size in ICON_SIZES:
        buffer = io.BytesIO()
        render_icon(size).save(buffer, format="PNG")
        entries.append((size, buffer.getvalue()))
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = len(header) + 16 * len(entries)
    directory, payload = b"", b""
    for size, data in entries:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(payload))
        payload += data
    Path(path).write_bytes(header + directory + payload)


def system_icon_sizes() -> tuple[int, int]:
    """(kleines, großes) Symbol in Pixeln für die aktuelle Bildschirmskalierung."""
    metrics = ctypes.windll.user32.GetSystemMetrics
    return metrics(SM_CXSMICON), metrics(SM_CXICON)


def apply_window_icon(window_handle: int, ico_path: Path) -> None:
    """Setzt kleines (Titelleiste) und großes Symbol (Taskleiste) in exakt passender Pixelgröße aus der .ico."""
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    small, big = system_icon_sizes()
    for kind, size in ((ICON_SMALL, small), (ICON_BIG, big)):
        handle = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, size, size, LR_LOADFROMFILE)
        user32.SendMessageW(window_handle, WM_SETICON, kind, handle)
