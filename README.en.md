# LuxPC

[Deutsch](README.md)

Automatically adjusts the screen brightness on Windows to the ambient light, using the webcam as a light meter. Brightness changes in small steps, never abruptly.

## Installation (3 steps)

1. Install [Python](https://www.python.org/downloads/) (tick "Add Python to PATH" during setup).
2. Download this project (green "Code" button → "Download ZIP") and extract it.
3. Double-click `build.bat`. Afterwards `LuxPC.exe` is in the folder.

`LuxPC.exe` runs on any Windows 10/11 computer without further installation and can be copied freely.

## Usage

- The sun icon in the notification area (next to the clock) opens the settings with one click.
- **Calibrate:** Under the respective light, set the suitable brightness and press "Set this brightness as a point now" – as often as you like under different light. The app shows the curve through all points; a click into the curve also adds a point.
- The camera is active only briefly per measurement. If another program (Zoom, Teams …) uses the camera, LuxPC pauses by itself.
- The interface language follows Windows by default and can be changed at the bottom of the settings window (German/English).

Settings are stored in `%APPDATA%\LuxPC\settings.json`.

## License

Copyright © 2026 Paul Teumer. Licensed under the [GNU General Public License v3.0](LICENSE).
