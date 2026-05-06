@echo off
chcp 65001 >nul
echo.
echo === 本地語音轉文字稿工具 ===
echo.
cd /d "%~dp0"
python transcribe_local.py
echo.
pause
