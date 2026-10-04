# LuxPC

[English](README.md)

**Automatische Bildschirmhelligkeit für Windows-PCs ohne Helligkeitssensor** – die Webcam dient als Umgebungslichtsensor. Die Helligkeit ändert sich in kleinen Schritten, nie ruckartig.

Geeignet für Desktop-PCs mit externem Monitor und für Laptops ohne Lichtsensor („Adaptive Helligkeit“ gibt es dort nicht). Läuft unauffällig im Infobereich, ohne Installation und ohne Konto.

## Installation

**Am einfachsten:** [`LuxPC.exe` von der Release-Seite herunterladen](https://github.com/paul-teumer/LuxPC/releases/latest) und doppelklicken. Python wird nicht benötigt, die Datei läuft auf jedem Windows-10/11-Rechner und kann beliebig kopiert werden.

**Selbst bauen (3 Schritte):**

1. [Python](https://www.python.org/downloads/) installieren (beim Installieren „Add Python to PATH“ anhaken).
2. Dieses Projekt herunterladen (grüner Knopf „Code“ → „Download ZIP“) und entpacken.
3. `build.bat` doppelklicken. Danach liegt `LuxPC.exe` im Ordner.

## Benutzung

- Das Sonnensymbol im Infobereich (neben der Uhr) öffnet mit einem Klick die Einstellungen.
- **Kalibrieren:** Bei dem jeweiligen Licht die passende Helligkeit einstellen und „Als Punkt festlegen“ drücken – beliebig oft bei verschiedenem Licht. Die Kurve durch alle Punkte zeigt die App an; ein Klick hinein setzt ebenfalls einen Punkt.
- Die Kamera ist nur kurz pro Messung aktiv. Nutzt ein anderes Programm (Zoom, Teams …) die Kamera, pausiert LuxPC von selbst.

Die Sprache (Deutsch/Englisch) folgt standardmäßig Windows und lässt sich unten im Einstellungsfenster umstellen.
Die Einstellungen liegen in `%APPDATA%\LuxPC\settings.json`.

## Für Entwickler

| Modul | Aufgabe |
|---|---|
| `service` | Regelkreis: Messung, Glättung, Helligkeitsrampe |
| `camera`, `metering`, `dshow` | Webcam als Belichtungsmesser (Belichtungswert in EV) |
| `camera_usage` | Erkennt, ob ein anderes Programm die Kamera nutzt |
| `mapping` | Kalibrierkurve, Glättung, Rampe |
| `config` | Einstellungen und Kalibrierpunkte (JSON) |
| `i18n` | Texte der Oberfläche in Deutsch und Englisch |
| `ui`, `chart`, `icon`, `app` | Fenster, Diagramme, Symbol, Programmstart mit Infobereich-Symbol |


```powershell
pip install -r requirements-dev.txt
python main.pyw      # direkt starten
python -m pytest     # Tests
```

## Lizenz

Copyright © 2026 Paul Teumer. Lizenziert unter der [GNU General Public License v3.0](LICENSE).
