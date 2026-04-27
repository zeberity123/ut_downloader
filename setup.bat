@echo off
REM ut_download — install dependencies. Made by Daru.
echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Done. Run the app:    python app.py
echo Build single exe:     build.bat
pause
