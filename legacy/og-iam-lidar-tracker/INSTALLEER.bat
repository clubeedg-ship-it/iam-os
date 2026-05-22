@echo off
title IAM LiDAR Tracker - Installatie
color 0A
echo.
echo  ========================================
echo   IAM LiDAR Tracker — Installatie
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [FOUT] Python niet gevonden!
    echo  Download van https://www.python.org/downloads/
    echo  Vink "Add Python to PATH" aan!
    pause & exit /b 1
)
echo  [OK] Python gevonden:
python --version
echo.

:: Installeer pakketten een voor een
echo  Pakketten installeren...
echo.

pip install pyrplidar --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (echo  [!] pyrplidar installatie probleem) else (echo  [OK] pyrplidar)

pip install pyserial --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (echo  [!] pyserial installatie probleem) else (echo  [OK] pyserial)

pip install numpy --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (echo  [!] numpy installatie probleem) else (echo  [OK] numpy)

pip install opencv-python --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (echo  [!] opencv-python installatie probleem) else (echo  [OK] opencv-python)

pip install python-osc --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (echo  [!] python-osc installatie probleem) else (echo  [OK] python-osc)

:: Ruim oude settings op
echo.
if exist iam_lidar_settings.json (
    del iam_lidar_settings.json
    echo  [OK] Oud instellingenbestand verwijderd
)

:: Verificatie
echo.
echo  Verificatie...
python -c "from pyrplidar import PyRPlidar; print('  [OK] pyrplidar werkt')" 2>nul || echo  [FOUT] pyrplidar werkt niet
python -c "import cv2; print('  [OK] opencv werkt')" 2>nul || echo  [FOUT] opencv werkt niet
python -c "from pythonosc import udp_client; print('  [OK] python-osc werkt')" 2>nul || echo  [FOUT] python-osc werkt niet
python -c "import serial; print('  [OK] pyserial werkt')" 2>nul || echo  [FOUT] pyserial werkt niet

echo.
echo  ========================================
echo   Installatie voltooid!
echo  ========================================
echo.
echo  Start met:     START.bat          (alleen tracker)
echo  Of met:        START_ALLES.bat    (tracker + menu)
echo.
pause
