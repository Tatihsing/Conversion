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
set EXIT_CODE=%errorlevel%

:: exit code 2 = Python 已下載更新，bat 接手套用並重啟
if %EXIT_CODE%==2 goto :do_update

if %EXIT_CODE%==1 (
    echo.
    echo [ERR] An error occurred.
)
pause
goto :eof

:do_update
echo.
echo ============================================================
echo   套用更新中，請稍候...
echo ============================================================
echo.

set "STAGING=%~dp0_update_staging"
set "REPO_FOLDER=%STAGING%\Conversion-main"
set "NEW_CORE=%REPO_FOLDER%\core"

:: 確認暫存資料夾存在
if not exist "%NEW_CORE%" (
    echo [ERR] 找不到更新暫存資料夾，更新失敗。
    pause
    goto :eof
)

:: 用 xcopy 逐檔覆蓋（比刪除整個資料夾更安全，中途失敗不會遺失舊版）
echo [1/4] 套用新版程式...
xcopy /R /S /E /Y /Q "%NEW_CORE%\*" "%~dp0core\" >nul
if errorlevel 1 (
    echo [ERR] 無法套用新版 core，請嘗試手動更新。
    pause
    goto :eof
)

:: 更新外層腳本（啟動.bat、README.md）
echo [2/4] 更新啟動腳本...
for %%F in (啟動.bat README.md) do (
    if exist "%REPO_FOLDER%\%%F" (
        xcopy /R /Y /Q "%REPO_FOLDER%\%%F" "%~dp0" >nul
    )
)
:: start.bat 最後才更新（正在執行中，新版在本次重啟後生效）
if exist "%REPO_FOLDER%\start.bat" (
    copy /y "%REPO_FOLDER%\start.bat" "%~dp0start.bat.new" >nul
    move /y "%~dp0start.bat.new" "%~dp0start.bat" >nul 2>&1
)

:: 清除暫存
echo [3/3] 清理暫存檔案...
rmdir /s /q "%STAGING%" 2>nul

echo.
echo ============================================================
echo   更新完成！請重新開啟「轉換程式.exe」即可使用新版。
echo ============================================================
echo.
pause

