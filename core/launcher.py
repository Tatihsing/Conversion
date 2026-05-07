"""
launcher.py
統一選單啟動器：所有功能的單一入口
"""

import sys
import os
import subprocess
import warnings

# 抑制套件警告（避免嚇到使用者）
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*urllib3.*")
warnings.filterwarnings("ignore", message=".*RequestsDependencyWarning.*")

# 強制 stdout/stderr 使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 確保 core 目錄可以被 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ensure_base_packages():
    """確保基本套件已安裝（google-generativeai, openpyxl, python-docx）"""
    packages = {
        "google.generativeai": "google-generativeai",
        "openpyxl": "openpyxl",
        "docx": "python-docx",
        "googleapiclient": "google-api-python-client",
        "google_auth_oauthlib": "google-auth-oauthlib",
        "google_auth_httplib2": "google-auth-httplib2",
    }
    missing = []
    for module, package in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        return

    print("\n[SETUP] 首次使用，安裝必要套件中...")
    for pkg in missing:
        print(f"  安裝 {pkg}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            print("OK")
        else:
            print("失敗")
            print(f"  [ERR] 請手動執行：pip install {pkg}")
    print()


def ensure_ffmpeg():
    """確保 ffmpeg 可用，若無則自動下載免安裝版至 tools/ 目錄"""
    from core.transcribe_cloud import _find_ffmpeg
    ffmpeg_path, ffprobe_path = _find_ffmpeg()
    if ffmpeg_path and ffprobe_path:
        return

    print("\n[SETUP] 首次使用，下載音訊處理套件 (ffmpeg) 中（約 40MB），請稍候...")
    import urllib.request
    import zipfile
    import tempfile
    import shutil
    from pathlib import Path
    
    url = "https://github.com/GyanD/codexffmpeg/releases/download/7.0.1/ffmpeg-7.0.1-essentials_build.zip"
    root_dir = Path(__file__).parent.parent
    tools_dir = root_dir / "tools"
    tools_dir.mkdir(exist_ok=True)
    zip_path = tools_dir / "ffmpeg.zip"
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        print("  正在解壓縮...")
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # 尋找解壓縮後的 bin 資料夾
            for root, dirs, files in os.walk(temp_dir):
                if "ffmpeg.exe" in files and "ffprobe.exe" in files:
                    shutil.copy2(os.path.join(root, "ffmpeg.exe"), tools_dir / "ffmpeg.exe")
                    shutil.copy2(os.path.join(root, "ffprobe.exe"), tools_dir / "ffprobe.exe")
                    break
        print("  [OK] ffmpeg 下載完成！長音訊支援已啟用。")
    except Exception as e:
        print(f"  [ERR] ffmpeg 下載失敗：{e}。長音訊切片功能可能會受限。")
    finally:
        if zip_path.exists():
            try:
                os.remove(zip_path)
            except Exception:
                pass


def show_menu():
    """顯示主選單"""
    from core.shared import API_KEYS_FILE

    # 檢查 API Key 狀態
    key_count = 0
    if API_KEYS_FILE.exists():
        for line in API_KEYS_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                key_count += 1

    key_status = f"（已設定 {key_count} 組）" if key_count > 0 else "（未設定，功能 1/2 無法使用）"

    # 取得版本與檢查更新
    from core.updater import get_version_string, check_for_updates
    version = get_version_string()
    
    print()
    print("=" * 55)
    print(f"  會議記錄工具箱 {version}")
    print("=" * 55)
    print()
    print("  請選擇功能：")
    print()
    print("  [1]  全自動會議記錄  （錄音/逐字稿 → HTML + Word）")
    print("  [2]  純轉逐字稿      （錄音 → 文字稿，使用 Gemini）")
    print("  [3]  離線轉逐字稿    （錄音 → 文字稿，不需網路）")
    print("  [4]  產生 SRT 字幕   （影音 → SRT 字幕檔）")
    print("  [5]  重新產生        （修改後重新產出 HTML/Word/PDF）")
    print()
    print(f"  API Key：{key_status}")
    print()
    print("  [Q]  離開")
    print()


def main():
    """主程式入口"""
    # 安裝基本套件
    ensure_base_packages()
    
    # 確保 ffmpeg 存在
    ensure_ffmpeg()

    # 取得版號並印出
    from core.updater import get_version_string, check_for_updates
    version = get_version_string()
    print(f"\n[INFO] 會議記錄工具箱 {version}")

    # 啟動時檢查更新（取消靜默，讓使用者知道有在檢查）
    print("[INFO] 檢查最新版本中...", end=" ", flush=True)
    check_for_updates(silent=False)
    print()

    # 如果有傳入檔案路徑（拖曳檔案到 .bat 上），依檔案類型決定動作
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if not os.path.isfile(file_path):
            print(f"  [ERR] 找不到檔案：{file_path}")
            return

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.json':
            # 拖曳 JSON → 重新產生 HTML/Word/PDF
            print(f"\n  📂 偵測到資料檔：{os.path.basename(file_path)}")
            from core.legacy.rebuild import _rebuild_from_json_path
            _rebuild_from_json_path(file_path)

        elif ext in ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac', '.txt'):
            # 拖曳音訊/逐字稿 → 全自動會議記錄
            print(f"\n  🎤 偵測到錄音/逐字稿：{os.path.basename(file_path)}")
            print(  "  自動執行全自動會議記錄...\n")
            from core import pipeline
            pipeline.run(file_path=file_path)

        else:
            print(f"\n  [ERR] 不支援的檔案格式：{ext}")
            print(f"  支援格式：")
            print(f"    音訊/逐字稿：.mp3 .m4a .wav .aac .flac .txt")
            print(f"    資料檔：    .json（_data.json）")

        return

    # 正常模式：直接執行全自動會議記錄 (傻瓜化設計)
    print("\n  🚀 啟動全自動會議記錄系統...")
    from core import pipeline
    pipeline.run()
    
    print("\n" + "=" * 50)
    print("  ✅ 處理完畢，請檢視產出的會議記錄！")
    print("=" * 50)


if __name__ == '__main__':
    main()

