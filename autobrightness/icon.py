"""Programm-Symbol: Sonne, zur Laufzeit gezeichnet (keine Bilddateien nötig)."""

from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageDraw

SUPERSAMPLING = 4


def render_icon(size: int = 64, png_base64: bool = False):
    """PIL-Bild der Sonne; mit png_base64=True als Base64-PNG-Text (für tkinter.PhotoImage)."""
    canvas = size * SUPERSAMPLING
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = canvas / 2
    radius = canvas * 0.22
    ray_inner, ray_outer = canvas * 0.32, canvas * 0.46
    for index in range(8):
        angle = index * math.pi / 4
        draw.line(
            (
                center + ray_inner * math.cos(angle), center + ray_inner * math.sin(angle),
                center + ray_outer * math.cos(angle), center + ray_outer * math.sin(angle),
            ),
            fill=(245, 165, 36, 255), width=max(2, int(canvas * 0.07)),
        )
    draw.ellipse((center - radius, center - radius, center + radius, center + radius), fill=(245, 165, 36, 255))
    image = image.resize((size, size), Image.LANCZOS)
    if not png_base64:
        return image
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
