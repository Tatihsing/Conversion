@echo off
chcp 65001 >nul 2>&1
title 會議記錄系統 - 一鍵修復更新工具
cd /d "%~dp0"

echo.
echo ========================================================
echo   會議記錄系統 - 一鍵修復更新工具
echo ========================================================
echo.
echo   此補丁將把程式升級至最新版本，
echo   完成後即可透過轉換程式.exe 自動更新。
echo.
echo   請確認「轉換程式.exe」目前沒有在執行中。
echo.
pause

:: 確認 core 資料夾存在（防止放錯位置）
if not exist "%~dp0core" (
    echo.
    echo [ERR] 找不到 core 資料夾！
    echo       請確認此補丁與「轉換程式.exe」放在同一個資料夾。
    echo.
    pause
    exit
)

:: 確認 Python 環境存在
if not exist "%~dp0python\python.exe" (
    echo.
    echo [ERR] 找不到 Python 環境！
    echo       請先執行一次「轉換程式.exe」讓它自動安裝環境後，再執行此補丁。
    echo.
    pause
    exit
)

echo.
echo [1/4] 下載最新版本中，請稍候...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Tatihsing/Conversion/archive/refs/heads/main.zip' -OutFile '%~dp0_patch.zip'"
if not exist "%~dp0_patch.zip" (
    echo.
    echo [ERR] 下載失敗，請確認網路連線後再試。
    pause
    exit
)

echo [2/4] 解壓縮中...
powershell -Command "Expand-Archive -Path '%~dp0_patch.zip' -DestinationPath '%~dp0_patch_temp' -Force"
if not exist "%~dp0_patch_temp\Conversion-main\core" (
    echo.
    echo [ERR] 解壓縮失敗或檔案結構異常。
    if exist "%~dp0_patch.zip" del "%~dp0_patch.zip"
    if exist "%~dp0_patch_temp" rmdir /s /q "%~dp0_patch_temp"
    pause
    exit
)

echo [3/4] 套用更新中...
xcopy /R /S /E /Y /Q "%~dp0_patch_temp\Conversion-main\core\*" "%~dp0core\" >nul
xcopy /R /Y /Q "%~dp0_patch_temp\Conversion-main\start.bat" "%~dp0" >nul
xcopy /R /Y /Q "%~dp0_patch_temp\Conversion-main\啟動.bat" "%~dp0" >nul
if exist "%~dp0_patch_temp\Conversion-main\README.md" (
    xcopy /R /Y /Q "%~dp0_patch_temp\Conversion-main\README.md" "%~dp0" >nul
)

echo [4/4] 清理暫存檔案...
del "%~dp0_patch.zip" 2>nul
rmdir /s /q "%~dp0_patch_temp" 2>nul

echo.
echo ========================================================
echo   更新完成！
echo ========================================================
echo.
echo   程式已升級至最新版本。
echo   之後直接開啟「轉換程式.exe」即可，有新版本時會自動提示更新。
echo.
pause
