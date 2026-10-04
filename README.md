# AutoBrightness

Passt die Bildschirmhelligkeit unter Windows automatisch an das Umgebungslicht an – gemessen mit der Webcam, die dafür als Belichtungsmesser dient.

*Windows tray app that sets monitor brightness from ambient light, measured by the webcam's exposure time.*

## Funktionsweise

Frühere Ansätze werten den Weißanteil bzw. die mittlere Pixelhelligkeit des Kamerabilds aus. Das ist unbrauchbar, weil die Kamera ihre Belichtung selbst nachregelt und so ein dunkler Raum fast genauso „hell“ im Bild erscheint wie ein heller.

AutoBrightness übernimmt deshalb die Belichtungsregelung selbst (DirectShow `IAMCameraControl`) und rechnet wie ein Belichtungsmesser:

```
Belichtungswert [EV] = log2(lineare Bildhelligkeit) − log2(Belichtungszeit in s)
```

Laptop-Kameras haben feste Blende und festen Gain; die Szenenhelligkeit folgt damit allein aus Bildhelligkeit und Belichtungszeit. Eine Verdopplung des Umgebungslichts entspricht genau +1 EV. Der Messbereich (je nach Kamera ca. 13 Blendenstufen) wird über Belichtungszeiten von 1/1024 s bis 1/4 s abgedeckt. Anschließend wird der Wert geglättet und linear in Blendenstufen auf den Helligkeitsbereich des Bildschirms abgebildet.

Beim Pausieren und Beenden wird die Kamera in die Belichtungsautomatik zurückversetzt.

## Installation

Voraussetzungen: Windows 10/11, Python 3.10+, Bildschirm mit DDC/CI (externe Monitore) oder interner Laptop-Bildschirm.

```powershell
pip install -r requirements.txt
python main.pyw
```

Eine eigenständige `AutoBrightness.exe` entsteht mit `./build.ps1` (Ergebnis in `dist/`).

## Bedienung

- Symbol im Infobereich: Klick öffnet die Einstellungen, Rechtsklick das Menü.
- **Kalibrierung:** In der dunkelsten gewünschten Umgebung „Jetzt = dunkel“, in der hellsten „Jetzt = hell“ drücken. Dazwischen wird interpoliert.
- **Helligkeitsbereich:** Minimum, Maximum und fester Versatz.
- **Verhalten:** Trägheit (Glättung), Messintervall, Mindeständerung gegen Flackern.
- **Nachtlicht:** Wärmerer Farbton über die Gamma-Rampe.
- Einstellungen liegen in `%APPDATA%\AutoBrightness\settings.json`.

## Hinweise

- Die Kamera-LED leuchtet, solange die Automatik aktiv ist; „Automatik“ pausieren gibt die Kamera frei.
- Die Kamera misst, was sie sieht (Gesicht, Raum, Bildschirmschein), nicht die Beleuchtungsstärke am Display. Die Kalibrierung gleicht das für den eigenen Arbeitsplatz aus.
- Kameras ohne Belichtungssteuerung fallen auf die Bildhelligkeit zurück; die App weist dann auf die ungenaue Messung hin.

## Entwicklung

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

## Lizenz

Copyright © 2026 Paul Teumer. Lizenziert unter der [GNU General Public License v3.0](LICENSE).
