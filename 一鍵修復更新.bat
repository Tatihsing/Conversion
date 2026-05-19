@echo off
chcp 65001 >nul 2>&1
title Meeting Auto - Patch Tool
setlocal enabledelayedexpansion

echo.
echo ========================================================
echo   Meeting Auto - One-Click Patch Tool
echo ========================================================
echo.
echo   Please ensure the main program is NOT running.
echo.
pause

:: ── Step 1: Search for start.bat in common locations ────────────────────────
echo.
echo [1/5] Searching for Meeting Auto installation...
echo.

set FOUND_COUNT=0
set TEMP_LIST=%TEMP%\meeting_auto_found.txt
if exist "%TEMP_LIST%" del "%TEMP_LIST%"

:: Search common locations
for %%D in (
    "%USERPROFILE%\Desktop"
    "%USERPROFILE%\Documents"
    "%USERPROFILE%\Downloads"
    "C:\"
    "D:\"
    "E:\"
    "F:\"
) do (
    if exist "%%~D" (
        for /r "%%~D" %%F in (start.bat) do (
            set "CANDIDATE=%%~dpF"
            set "CANDIDATE=!CANDIDATE:~0,-1!"
            if exist "!CANDIDATE!\core" (
                if exist "!CANDIDATE!\python\python.exe" (
                    set /a FOUND_COUNT+=1
                    echo !FOUND_COUNT!. !CANDIDATE!>> "%TEMP_LIST%"
                    echo   Found [!FOUND_COUNT!]: !CANDIDATE!
                )
            )
        )
    )
)

if %FOUND_COUNT%==0 (
    echo.
    echo [ERR] No Meeting Auto installation found.
    echo       Make sure the program has been run at least once.
    echo.
    pause
    exit
)

:: ── Step 2: Let user pick if multiple found ──────────────────────────────────
echo.
if %FOUND_COUNT%==1 (
    set /p TARGET_DIR=< "%TEMP_LIST%"
    set TARGET_DIR=!TARGET_DIR:~3!
    echo   Using: !TARGET_DIR!
) else (
    echo   Found %FOUND_COUNT% installations. Enter number to select:
    echo.
    set /p CHOICE="  Your choice: "
    set LINE_NUM=0
    for /f "tokens=*" %%L in (%TEMP_LIST%) do (
        set /a LINE_NUM+=1
        if !LINE_NUM!==!CHOICE! (
            set TARGET_LINE=%%L
        )
    )
    set TARGET_DIR=!TARGET_LINE:~3!
    echo   Selected: !TARGET_DIR!
)

del "%TEMP_LIST%" 2>nul

if not defined TARGET_DIR (
    echo [ERR] Invalid selection.
    pause
    exit
)

echo.
echo [2/5] Downloading latest version, please wait...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Tatihsing/Conversion/archive/refs/heads/main.zip' -OutFile '!TARGET_DIR!\_patch.zip'"
if not exist "!TARGET_DIR!\_patch.zip" (
    echo.
    echo [ERR] Download failed.
    pause
    exit
)

echo [3/5] Extracting...
powershell -Command "Expand-Archive -Path '!TARGET_DIR!\_patch.zip' -DestinationPath '!TARGET_DIR!\_patch_temp' -Force"
if not exist "!TARGET_DIR!\_patch_temp\Conversion-main\core" (
    echo.
    echo [ERR] Extraction failed.
    if exist "!TARGET_DIR!\_patch.zip" del "!TARGET_DIR!\_patch.zip"
    if exist "!TARGET_DIR!\_patch_temp" rmdir /s /q "!TARGET_DIR!\_patch_temp"
    pause
    exit
)

echo [4/5] Applying update...
xcopy /R /S /E /Y /Q "!TARGET_DIR!\_patch_temp\Conversion-main\core\*" "!TARGET_DIR!\core\" >nul
xcopy /R /Y /Q "!TARGET_DIR!\_patch_temp\Conversion-main\start.bat" "!TARGET_DIR!\" >nul
xcopy /R /Y /Q "!TARGET_DIR!\_patch_temp\Conversion-main\啟動.bat" "!TARGET_DIR!\" >nul
if exist "!TARGET_DIR!\_patch_temp\Conversion-main\README.md" (
    xcopy /R /Y /Q "!TARGET_DIR!\_patch_temp\Conversion-main\README.md" "!TARGET_DIR!\" >nul
)

echo [5/5] Cleaning up...
del "!TARGET_DIR!\_patch.zip" 2>nul
rmdir /s /q "!TARGET_DIR!\_patch_temp" 2>nul

echo.
echo ========================================================
echo   Update Completed!
echo ========================================================
echo.
echo   You can now run Meeting Auto normally.
echo.
pause