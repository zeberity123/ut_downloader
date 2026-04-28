@echo off
REM Build single-file Windows exe — size-optimized.
REM Bundles ffmpeg if it's next to this script; otherwise uses PATH at runtime.

setlocal

REM Make sure logo.ico exists so the exe gets a proper icon.
if not exist "logo.ico" (
    echo Generating logo.ico...
    python generate_logo.py
)

set ADD_BIN=
if exist "ffmpeg.exe" (
    echo Bundling ffmpeg.exe into the build...
    set ADD_BIN=--add-binary "ffmpeg.exe;."
) else (
    echo ffmpeg.exe not in the current folder; the exe will rely on PATH.
)

python -m PyInstaller --noconfirm --onefile --windowed --clean ^
    --name ut_download ^
    --icon logo.ico ^
    --add-data "logo.ico;." ^
    --collect-all yt_dlp ^
    --collect-all qfluentwidgets ^
    --collect-all qframelesswindow ^
    --collect-all darkdetect ^
    %ADD_BIN% ^
    --exclude-module PyQt5.Qt3DAnimation ^
    --exclude-module PyQt5.Qt3DCore ^
    --exclude-module PyQt5.Qt3DExtras ^
    --exclude-module PyQt5.Qt3DInput ^
    --exclude-module PyQt5.Qt3DLogic ^
    --exclude-module PyQt5.Qt3DRender ^
    --exclude-module PyQt5.QAxContainer ^
    --exclude-module PyQt5.QtBluetooth ^
    --exclude-module PyQt5.QtCharts ^
    --exclude-module PyQt5.QtDataVisualization ^
    --exclude-module PyQt5.QtDBus ^
    --exclude-module PyQt5.QtDesigner ^
    --exclude-module PyQt5.QtHelp ^
    --exclude-module PyQt5.QtLocation ^
    --exclude-module PyQt5.QtNetworkAuth ^
    --exclude-module PyQt5.QtNfc ^
    --exclude-module PyQt5.QtOpenGL ^
    --exclude-module PyQt5.QtPositioning ^
    --exclude-module PyQt5.QtPrintSupport ^
    --exclude-module PyQt5.QtQml ^
    --exclude-module PyQt5.QtQuick ^
    --exclude-module PyQt5.QtQuick3D ^
    --exclude-module PyQt5.QtQuickWidgets ^
    --exclude-module PyQt5.QtRemoteObjects ^
    --exclude-module PyQt5.QtScxml ^
    --exclude-module PyQt5.QtSensors ^
    --exclude-module PyQt5.QtSerialPort ^
    --exclude-module PyQt5.QtSql ^
    --exclude-module PyQt5.QtSvg ^
    --exclude-module PyQt5.QtTest ^
    --exclude-module PyQt5.QtWebChannel ^
    --exclude-module PyQt5.QtWebEngine ^
    --exclude-module PyQt5.QtWebEngineCore ^
    --exclude-module PyQt5.QtWebEngineWidgets ^
    --exclude-module PyQt5.QtWebSockets ^
    --exclude-module PyQt5.QtX11Extras ^
    --exclude-module PyQt5.QtXmlPatterns ^
    --exclude-module PyQtWebEngine ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module test ^
    --exclude-module pytest ^
    --exclude-module doctest ^
    --exclude-module pdb ^
    --exclude-module pydoc ^
    --exclude-module setuptools ^
    --exclude-module pip ^
    --exclude-module IPython ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module scipy ^
    --exclude-module pandas ^
    --exclude-module PIL ^
    --exclude-module cv2 ^
    app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo Build FAILED.
    echo ============================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo Build complete: dist\ut_download.exe
for %%I in (dist\ut_download.exe) do echo Size: %%~zI bytes (%%~zI / 1048576 MB approx)
echo ============================================================
pause
