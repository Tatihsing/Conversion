@echo off
echo.
echo === Setup Gemini API Key ===
echo.
echo Get your key at: https://aistudio.google.com/apikey
echo.
echo Opening api_keys.txt - paste your key(s) and save the file.
echo.
notepad "%~dp0..\api_keys.txt"
echo.
echo Done. Run 03_run.bat to start.
pause
