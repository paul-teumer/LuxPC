# AutoBrightness

Stellt die Bildschirmhelligkeit unter Windows automatisch passend zum Umgebungslicht ein – die Webcam dient dabei als Lichtmesser. Die Helligkeit ändert sich in kleinen Schritten, nie ruckartig.

## Installation (3 Schritte)

1. [Python](https://www.python.org/downloads/) installieren (beim Installieren „Add Python to PATH“ anhaken).
2. Dieses Projekt herunterladen (grüner Knopf „Code“ → „Download ZIP“) und entpacken.
3. `build.bat` doppelklicken. Danach liegt `AutoBrightness.exe` im Ordner.

Die `AutoBrightness.exe` läuft auf jedem Windows-10/11-Rechner ohne weitere Installation und kann beliebig kopiert werden.

## Benutzung

- Das Sonnensymbol im Infobereich (neben der Uhr) öffnet mit einem Klick die Einstellungen.
- **Kalibrieren:** Bei dem jeweiligen Licht die passende Helligkeit einstellen und „Als Punkt festlegen“ drücken – beliebig oft bei verschiedenem Licht. Die Kurve durch alle Punkte zeigt die App an; ein Klick hinein setzt ebenfalls einen Punkt.
- Die Kamera ist nur kurz pro Messung aktiv. Nutzt ein anderes Programm (Zoom, Teams …) die Kamera, pausiert AutoBrightness von selbst.

Die Einstellungen liegen in `%APPDATA%\AutoBrightness\settings.json`.

## Für Entwickler

```powershell
pip install -r requirements-dev.txt
python main.pyw      # direkt starten
python -m pytest     # Tests
```

## Lizenz

Copyright © 2026 Paul Teumer. Lizenziert unter der [GNU General Public License v3.0](LICENSE).
