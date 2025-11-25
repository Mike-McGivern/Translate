@echo off
echo ================================================
echo jimakuChan Hardware Speech Capture
echo Desktop application for high-quality speech recognition
echo ================================================
echo.

cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/
    pause
    exit /b 1
)

REM Check if requirements are installed
echo Checking dependencies...
python -c "import sounddevice, faster_whisper, websockets" 2>nul
if errorlevel 1 (
    echo.
    echo Installing required dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo.
echo Starting speech capture application...
echo Press Ctrl+C to stop
echo.

python speech_capture.py

pause
