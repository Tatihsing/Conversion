@echo off
echo.
echo === Meeting Minutes Auto Pipeline ===
echo.

cd /d "%~dp0"

python "%~dp0full_pipeline.py"

echo.
pause
