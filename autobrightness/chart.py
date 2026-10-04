"""Kantenglättendes Zeichnen für Diagramme: vierfach überabgetastet, dann auf Zielgröße verkleinert."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageTk

SUPERSAMPLING = 4
FONT_FILE = "segoeui.ttf"


class Painter:
    """Zeichnet in Zeichenflächen-Pixeln (Breite x Höhe) und liefert ein scharfes, geglättetes Bild."""

    def __init__(self, width: int, height: int, background: str) -> None:
        self.width, self.height = width, height
        self._image = Image.new("RGB", (width * SUPERSAMPLING, height * SUPERSAMPLING), background)
        self._draw = ImageDraw.Draw(self._image)

    def _scaled(self, points: Sequence[float]) -> list[float]:
        return [value * SUPERSAMPLING for value in points]

    def line(self, points: Sequence[float], color: str, width: float = 1.0) -> None:
        """Linienzug aus abwechselnden x/y-Werten mit runden Enden und Gelenken."""
        scaled = self._scaled(points)
        pixel_width = max(1, round(width * SUPERSAMPLING))
        self._draw.line(scaled, fill=color, width=pixel_width, joint="curve")
        radius = pixel_width / 2
        for x, y in zip(scaled[0::2], scaled[1::2]):
            if x in (scaled[0], scaled[-2]) and y in (scaled[1], scaled[-1]):
                self._draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def dashed_line(self, start: tuple[float, float], end: tuple[float, float], color: str, width: float = 1.0, dash: float = 3.0) -> None:
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        for offset in range(0, int(length / dash), 2):
            begin, finish = offset * dash / length, min(length, (offset + 1) * dash) / length
            self.line(
                [start[0] + (end[0] - start[0]) * begin, start[1] + (end[1] - start[1]) * begin,
                 start[0] + (end[0] - start[0]) * finish, start[1] + (end[1] - start[1]) * finish],
                color, width,
            )

    def circle(self, x: float, y: float, radius: float, fill: str | None = None, outline: str | None = None, width: float = 1.0) -> None:
        scaled = self._scaled((x - radius, y - radius, x + radius, y + radius))
        self._draw.ellipse(scaled, fill=fill, outline=outline, width=round(width * SUPERSAMPLING))

    def text(self, x: float, y: float, text: str, color: str, size: int, anchor: str = "la") -> None:
        try:
            font = ImageFont.truetype(FONT_FILE, size * SUPERSAMPLING)
        except OSError:
            font = ImageFont.load_default()
        self._draw.text((x * SUPERSAMPLING, y * SUPERSAMPLING), text, fill=color, font=font, anchor=anchor)

    def show(self, canvas: tk.Canvas) -> None:
        image = self._image.resize((self.width, self.height), Image.LANCZOS)
        canvas.image = ImageTk.PhotoImage(image)
        canvas.delete("all")
        canvas.create_image(0, 0, image=canvas.image, anchor="nw")
