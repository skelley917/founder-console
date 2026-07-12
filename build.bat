@echo off
title Building Mission Control...

echo.
echo ====================================
echo Building Mission Control...
echo ====================================
echo.

py -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "MissionControl" ^
  src\app.py

echo.
echo ====================================
echo Build Complete!
echo ====================================
echo.

echo Executable:
echo dist\MissionControl.exe
echo.

pause