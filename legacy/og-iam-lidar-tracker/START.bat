@echo off
title IAM LiDAR Tracker
color 0B

:: Auto-detect COM poort
set COMPORT=
for /f "tokens=1" %%i in ('python -c "import serial.tools.list_ports; ports=[p.device for p in serial.tools.list_ports.comports() if 'CP210' in p.description or 'Silicon' in p.description]; print(ports[0] if ports else '')" 2^>nul') do set COMPORT=%%i

if "%COMPORT%"=="" (
    echo.
    echo  Geen RPLIDAR gevonden. Beschikbare poorten:
    python -c "import serial.tools.list_ports; [print(f'    {p.device} - {p.description}') for p in serial.tools.list_ports.comports()]" 2>nul
    echo.
    set /p COMPORT="  Typ poortnaam (bijv. COM3): "
)

echo.
echo  IAM LiDAR Tracker - %COMPORT%
echo.
python iam_lidar_tracker.py --port %COMPORT%
pause
