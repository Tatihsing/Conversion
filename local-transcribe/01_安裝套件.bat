@echo off
chcp 65001 >nul
echo.
echo ========================================
echo  本地語音轉文字 - 環境檢查與安裝
echo ========================================
echo.

REM ── 1. 確認 Python ───────────────────────────────────────────────────────────
echo [1/3] 確認 Python 版本...
python --version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERR] 找不到 Python！
    echo       請先安裝 Python 3.10 以上：
    echo       https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo       安裝時務必勾選「Add python.exe to PATH」
    echo.
    pause
    exit /b 1
)

REM ── 2. 安裝 faster-whisper ───────────────────────────────────────────────────
echo.
echo [2/3] 安裝 faster-whisper（含 ctranslate2）...
pip install faster-whisper
if %ERRORLEVEL% NEQ 0 (
    echo [ERR] 安裝失敗！請以系統管理員身份重新執行
    pause
    exit /b 1
)

REM ── 3. 驗證安裝 ─────────────────────────────────────────────────────────────
echo.
echo [3/3] 驗證安裝...
python -c "from faster_whisper import WhisperModel; print('[OK] faster-whisper 驗證成功！')"
if %ERRORLEVEL% NEQ 0 (
    echo [ERR] 驗證失敗，請重新執行本檔案
    pause
    exit /b 1
)

echo.
echo ========================================
echo  安裝完成！
echo.
echo  【GPU 加速說明】
echo  若您的電腦有 NVIDIA 顯示卡，程式會自動
echo  偵測並使用 GPU（需已安裝 NVIDIA 驅動）。
echo  若未偵測到 GPU，程式自動改用 CPU 執行。
echo  無需任何額外設定。
echo.
echo  請雙擊 02_執行轉錄.bat 開始使用
echo ========================================
echo.
pause
