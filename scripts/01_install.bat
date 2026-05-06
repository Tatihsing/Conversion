@echo off
echo.
echo === Install Required Packages ===
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] Installing google-generativeai ...
pip install google-generativeai

echo.
echo [2/2] Installing openpyxl ...
pip install openpyxl

echo.
echo === Done! Run 02_setup_api_key.bat next. ===
pause
