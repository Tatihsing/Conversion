@echo off
chcp 65001 >nul 2>&1
title Meeting Toolbox

:: Switch to script directory
cd /d "%~dp0"

:: Embedded Python paths
set "PYTHON_DIR=%~dp0python"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PYTHON_ZIP=%~dp0_python_embed.zip"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"

:: Check if embedded Python exists
if exist "%PYTHON_EXE%" goto :run

:: First-time setup: download Python
echo.
echo ============================================================
echo   First-time setup: downloading Python (~25 MB)
echo   This only runs once.
echo ============================================================
echo.

:: Check curl availability (built-in on Windows 10+)
where curl >nul 2>&1
if errorlevel 1 (
    echo [ERR] curl not found. Windows 10+ required.
    pause
    exit /b 1
)

:: Download Python embeddable package
echo [1/4] Downloading Python...
curl -L -o "%PYTHON_ZIP%" "%PYTHON_URL%" --progress-bar
if errorlevel 1 (
    echo [ERR] Download failed. Check your internet connection.
    if exist "%PYTHON_ZIP%" del "%PYTHON_ZIP%"
    pause
    exit /b 1
)

:: Extract
echo [2/4] Extracting...
mkdir "%PYTHON_DIR%" 2>nul
powershell -NoProfile -Command "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
if errorlevel 1 (
    echo [ERR] Extraction failed.
    pause
    exit /b 1
)
del "%PYTHON_ZIP%" 2>nul

:: Enable site-packages and add project root to Python path
echo [3/4] Configuring Python...
for %%f in ("%PYTHON_DIR%\python*._pth") do (
    echo ..>> "%%f"
    echo import site>> "%%f"
)

:: Install pip
echo [4/4] Installing pip...
curl -L -o "%PYTHON_DIR%\get-pip.py" "%GET_PIP_URL%" --silent
"%PYTHON_EXE%" "%PYTHON_DIR%\get-pip.py" --quiet
del "%PYTHON_DIR%\get-pip.py" 2>nul

echo.
echo [OK] Python setup complete!
echo.

:run
:: Set environment for Python
set "PYTHONPATH=%~dp0"
set "PYTHONUTF8=1"

:: Launch main program
:: If a file was dragged onto this bat, pass it as argument
if "%~1"=="" (
    "%PYTHON_EXE%" -u -m core.launcher
) else (
    "%PYTHON_EXE%" -u -m core.launcher "%~1"
)
if errorlevel 1 (
    echo.
    echo [ERR] An error occurred.
)
pause

