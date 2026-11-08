@echo off
REM Builds dist\TrafficMonitor.exe  (run from the project folder, inside your venv)
setlocal
echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt || goto :fail
echo [2/3] Generating icon...
python tools\make_icon.py || goto :fail
echo [3/3] Building EXE...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name TrafficMonitor --icon assets\icon.ico ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts ^
  main.py || goto :fail
echo.
echo Done: dist\TrafficMonitor.exe
exit /b 0
:fail
echo Build failed.
exit /b 1
