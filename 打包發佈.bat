@echo off
chcp 65001 >nul 2>&1
title Package Tool

cd /d "%~dp0"

set "DEST=%USERPROFILE%\Desktop\meeting-auto"

echo.
echo ============================================================
echo   Packaging meeting-auto for distribution
echo   Target: %DEST%
echo ============================================================
echo.

if exist "%DEST%" (
    echo [!] Target folder already exists. Will overwrite.
    echo.
    set /p confirm="  Continue? (Y/N): "
    if /i not "%confirm%"=="Y" (
        echo Cancelled.
        pause
        exit /b 0
    )
)

echo.
echo [1/5] Creating folders...
mkdir "%DEST%" 2>nul
mkdir "%DEST%\core" 2>nul
mkdir "%DEST%\output" 2>nul

echo [2/5] Copying launcher...
copy /y "%~dp0start.bat" "%DEST%\start.bat" >nul
copy /y "%~dp0start.bat" "%DEST%\啟動.bat" >nul
copy /y "README.md" "%DEST%\README.md" >nul

echo [3/6] Copying config...
copy /y "語音辨識對照表.xlsx" "%DEST%\語音辨識對照表.xlsx" >nul

:: Copy actual API keys file
if exist "api_keys.txt" (
    copy /y "api_keys.txt" "%DEST%\api_keys.txt" >nul
    echo        api_keys.txt copied ^(含現有 Key^)
) else (
    > "%DEST%\api_keys.txt" (
        echo # Gemini API Key
        echo # One key per line. Lines starting with # are ignored.
        echo # Get your key: https://aistudio.google.com/apikey
        echo.
    )
    echo        api_keys.txt ^(空白範本，請自行填入 Key^)
)

echo [4/6] Copying code...
copy /y "core\*.py" "%DEST%\core\" >nul

echo [5/6] Copying python environment (this may take a minute)...
mkdir "%DEST%\python" 2>nul
xcopy /s /e /y /q "python\*" "%DEST%\python\" >nul

echo [6/6] Done!
echo.
echo ============================================================
echo   Packaged to: %DEST%
echo.
echo   api_keys.txt 已一併複製。
echo   注意：此份包含你的 API Key，請勿傳給不信任的人。
echo ============================================================
echo.
pause
