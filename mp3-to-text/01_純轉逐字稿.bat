@echo off
echo.
echo === MP3 to Text Only ===
echo.
cd /d "%~dp0"
python transcribe_only.py
echo.
pause
