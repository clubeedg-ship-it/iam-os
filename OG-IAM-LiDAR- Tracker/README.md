# IAM LiDAR Tracker v2.0

Vervanging voor LidarTracker.exe. Simpel en betrouwbaar.

## Hoe het werkt

```
RPLIDAR S2 → iam_lidar_tracker.py → TUIO UDP:3333 → Electron tuio-bridge.js → WS:8765 → Games
```

De tracker stuurt TUIO. De Electron app heeft een eigen bridge die dit doorstuurt naar de games.
Er is GEEN aparte WebSocket server of tuio_bridge.py nodig.

## Bestanden

| Bestand | Functie |
|---|---|
| `iam_lidar_tracker.py` | Het programma (412 regels) |
| `calibration.json` | Kalibratie van je werkende origineel (6 presets) |
| `iam_lidar_calibration.json` | Actieve kalibratie ("training1") |
| `INSTALLEER.bat` | Eenmalig: installeert Python pakketten |
| `START.bat` | Start alleen de tracker |
| `START_ALLES.bat` | Start tracker + Electron menu samen |

## Eerste keer

1. Dubbelklik `INSTALLEER.bat`
2. Dubbelklik `START_ALLES.bat`

## Dagelijks gebruik

Dubbelklik `START_ALLES.bat` — klaar.

## Features

- Auto-detect COM poort (zoekt CP210x/Silicon Labs)
- Auto-detect baudrate (1000000 / 256000 / 115200)
- Auto-baseline na 3 seconden
- Importeert originele LidarTracker kalibratie
- Auto-reconnect bij sensor wegval
- Klikbare knoppen in operator venster
- TUIO 1.1 via python-osc (gegarandeerd correct formaat)
- FlipH + FlipV standaard aan (zoals origineel)
