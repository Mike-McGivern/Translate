@echo off
echo ================================================
echo VanillaChanny GUI Desktop Application
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

REM Check if GUI dependencies are installed
echo Checking GUI dependencies...
python -c "import customtkinter, flask" 2>nul
if errorlevel 1 (
    echo.
    echo Installing/updating GUI dependencies...
    pip install -r requirements_gui.txt
    if errorlevel 1 (
        echo.
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo.
echo Starting GUI application...
echo.

python gui_app.py

pause
