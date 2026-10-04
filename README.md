# LuxPC

[Deutsch](README.de.md)

**Automatic screen brightness for Windows PCs without a light sensor** – your webcam serves as the ambient light sensor. Brightness changes in small steps, never abruptly.

Made for desktop PCs with external monitors and for laptops without an ambient light sensor, where Windows' adaptive brightness is not available. Runs quietly in the notification area, needs no installation and no account.

## Installation

**Easiest:** [download `LuxPC.exe` from the latest release](https://github.com/paul-teumer/LuxPC/releases/latest) and double-click it. No Python needed; it runs on any Windows 10/11 computer and can be copied freely.

**Build it yourself (3 steps):**

1. Install [Python](https://www.python.org/downloads/) (tick "Add Python to PATH" during setup).
2. Download this project (green "Code" button → "Download ZIP") and extract it.
3. Double-click `build.bat`. Afterwards `LuxPC.exe` is in the folder.

## Usage

- The sun icon in the notification area (next to the clock) opens the settings with one click.
- **Calibrate:** Under the respective light, set the suitable brightness and press "Set this brightness as a point now" – as often as you like under different light. The app shows the curve through all points; a click into the curve also adds a point.
- The camera is active only briefly per measurement. If another program (Zoom, Teams …) uses the camera, LuxPC pauses by itself.
- The interface language follows Windows by default and can be changed at the bottom of the settings window (German/English).

Settings are stored in `%APPDATA%\LuxPC\settings.json`.

## For developers

| Module | Purpose |
|---|---|
| `service` | Control loop: measurement, smoothing, brightness ramp |
| `camera`, `metering`, `dshow` | Webcam as exposure meter (exposure value in EV) |
| `camera_usage` | Detects whether another program is using the camera |
| `mapping` | Calibration curve, smoothing, ramp |
| `config` | Settings and calibration points (JSON) |
| `i18n` | UI texts in German and English |
| `ui`, `chart`, `icon`, `app` | Window, charts, icon, startup with tray icon |

```powershell
pip install -r requirements-dev.txt
python main.pyw      # run directly
python -m pytest     # tests
```

## License

Copyright © 2026 Paul Teumer. Licensed under the [GNU General Public License v3.0](LICENSE).
