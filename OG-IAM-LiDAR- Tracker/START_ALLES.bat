@echo off
title IAM Systeem
color 0A

echo.
echo  ========================================
echo   IAM Systeem — Alles starten
echo  ========================================
echo.

:: ─── Configuratie ───
:: Pas deze paden aan als je bestanden ergens anders staan
set TRACKER_DIR=%~dp0
set MENU_DIR=C:\1finalmenuv2

:: ─── Check of mappen bestaan ───
if not exist "%TRACKER_DIR%iam_lidar_tracker.py" (
    echo  [FOUT] LiDAR tracker niet gevonden in %TRACKER_DIR%
    pause & exit /b 1
)
if not exist "%MENU_DIR%\package.json" (
    echo  [FOUT] Electron menu niet gevonden in %MENU_DIR%
    echo  Pas MENU_DIR aan in dit bestand.
    pause & exit /b 1
)

:: ─── Auto-detect COM poort ───
set COMPORT=
for /f "tokens=1" %%i in ('python -c "import serial.tools.list_ports; ports=[p.device for p in serial.tools.list_ports.comports() if 'CP210' in p.description or 'Silicon' in p.description]; print(ports[0] if ports else '')" 2^>nul') do set COMPORT=%%i

if "%COMPORT%"=="" (
    echo  [WAARSCHUWING] Geen RPLIDAR gevonden
    echo  Beschikbare poorten:
    python -c "import serial.tools.list_ports; [print(f'    {p.device} - {p.description}') for p in serial.tools.list_ports.comports()]" 2>nul
    echo.
    set /p COMPORT="  Typ poortnaam (bijv. COM3): "
)

:: ─── Start LiDAR tracker in apart venster ───
echo  [1/2] LiDAR tracker starten op %COMPORT%...
start "IAM LiDAR Tracker" cmd /k "cd /d %TRACKER_DIR% && python iam_lidar_tracker.py --port %COMPORT%"

:: Wacht 5 sec zodat de tracker baseline kan opnemen
echo  Wacht 5 seconden op auto-baseline...
timeout /t 5 /nobreak >nul

:: ─── Start Electron menu ───
echo  [2/2] Electron menu starten...
start "IAM Menu" cmd /k "cd /d %MENU_DIR% && npm start"

echo.
echo  ========================================
echo   Alles gestart!
echo   - LiDAR tracker draait (auto-baseline)
echo   - Electron menu start op
echo  ========================================
echo.
echo  Sluit dit venster als alles draait.
echo  Of druk een toets om te stoppen.
pause
