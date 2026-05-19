import os
import shutil
from pathlib import Path

# ── 打包說明 ──────────────────────────────────────────────────────────────────
# 自動更新機制說明：
#   - core/*.py、start.bat、啟動.bat 均可透過程式內建更新機制自動覆蓋，無鎖定問題。
#   - 【注意】轉換程式.exe 無法透過自動更新覆蓋（Windows 會鎖住執行中的 .exe）。
#     若 .exe 本身需要更新（例如換圖示、版本資訊），必須手動發布新的 .exe 給使用者替換。
#     建議的做法：讓 .exe 只作為啟動殼，所有邏輯保持在 core/*.py，盡量避免需要更換 .exe。
# ─────────────────────────────────────────────────────────────────────────────

def safe_copy(src, dst):
    if os.path.exists(dst):
        # 移除唯讀、隱藏與系統屬性 (解決 Windows 覆蓋隱藏檔案會發生 Permission Denied 的問題)
        os.system(f'attrib -h -r -s "{dst}" >nul 2>&1')
        try:
            os.chmod(dst, 0o777)
        except Exception:
            pass
    shutil.copy2(src, dst)

def build():
    # 設定路徑
    root_dir = Path(__file__).parent.parent
    dest_dir = root_dir / "錄音轉會議記錄"
    
    print("=" * 60)
    print(f"  Packaging meeting-auto for distribution")
    print(f"  Target: {dest_dir}")
    print("=" * 60)
    print()

    # 建立必要資料夾
    folders = ["core", "output", "python"]
    for f in folders:
        path = dest_dir / f
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"[SUCCESS] Created folder: {f}")

    # 複製啟動腳本
    safe_copy(root_dir / "start.bat", dest_dir / "start.bat")
    safe_copy(root_dir / "start.bat", dest_dir / "啟動.bat")
    if (root_dir / "README.md").exists():
        safe_copy(root_dir / "README.md", dest_dir / "README.md")
    if (root_dir / "更新程式.bat").exists():
        safe_copy(root_dir / "更新程式.bat", dest_dir / "更新程式.bat")
    if (root_dir / "轉換程式.exe").exists():
        safe_copy(root_dir / "轉換程式.exe", dest_dir / "轉換程式.exe")
    print("[SUCCESS] Copied: Launcher scripts, README, Update tool and 轉換程式.exe")

    # 複製設定檔 (保護使用者現有的對照表，避免覆蓋)
    excel_name = "語音辨識對照表.xlsx"
    if (root_dir / excel_name).exists():
        if not (dest_dir / excel_name).exists():
            safe_copy(root_dir / excel_name, dest_dir / excel_name)
            print(f"[SUCCESS] Copied: {excel_name}")
        else:
            print(f"[INFO] Skip: {excel_name} (Existing file detected, protecting user content)")

    # 複製 Google Drive 驗證檔
    for auth_file in ["credentials.json", "token.json"]:
        if (root_dir / auth_file).exists():
            safe_copy(root_dir / auth_file, dest_dir / auth_file)
            print(f"[SUCCESS] Copied: {auth_file}")

    # 處理 API Key
    api_key_src = root_dir / "api_keys.txt"
    api_key_dest = dest_dir / "api_keys.txt"
    if api_key_src.exists():
        safe_copy(api_key_src, api_key_dest)
        print("[SUCCESS] Copied: api_keys.txt (with existing keys)")
    else:
        if os.path.exists(api_key_dest):
            os.chmod(api_key_dest, 0o777)
        with open(api_key_dest, "w", encoding="utf-8") as f:
            f.write("# Gemini API Key\n# One key per line.\n\n")
        print("[SUCCESS] Created: api_keys.txt (template)")

    # 複製程式碼 (包含 version.txt)
    core_src = root_dir / "core"
    core_dest = dest_dir / "core"
    for py_file in core_src.glob("*.py"):
        safe_copy(py_file, core_dest / py_file.name)
    
    version_file = core_src / "version.txt"
    if version_file.exists():
        safe_copy(version_file, core_dest / "version.txt")
        print(f"[SUCCESS] Copied: Core files and version.txt ({version_file.read_text().strip()})")

    # 複製 使用說明.jpg
    if (root_dir / "使用說明.jpg").exists():
        safe_copy(root_dir / "使用說明.jpg", dest_dir / "使用說明.jpg")
        print("[SUCCESS] Copied: 使用說明.jpg")

    # 複製 legacy 資料夾 (包含備用引擎與工具)
    legacy_src = core_src / "legacy"
    legacy_dest = core_dest / "legacy"
    if legacy_src.exists():
        if not legacy_dest.exists():
            legacy_dest.mkdir(parents=True, exist_ok=True)
        for f in legacy_src.glob("*"):
            if f.is_file():
                safe_copy(f, legacy_dest / f.name)
        print("[SUCCESS] Copied: Core legacy files")

    # 複製 Python 環境 (xcopy 模擬)
    print("[INFO] Copying python environment (this may take a minute)...")
    py_src = root_dir / "python"
    py_dest = dest_dir / "python"
    
    # 使用 robocopy 效率更高且穩定
    os.system(f'robocopy "{py_src}" "{py_dest}" /E /Z /R:5 /W:5 /MT:32 /LOG:NUL /NFL /NDL')
    print("[SUCCESS] Copied: Python environment")

    # --- 隱藏系統檔案與資料夾 ---
    print("[INFO] Hiding system files and folders for a cleaner view...")
    visible_files = ["使用說明.jpg", "README.md", "轉換程式.exe", "語音辨識對照表.xlsx"]
    
    # 遍歷目標資料夾中的所有項目
    for item in dest_dir.glob("*"):
        if item.name not in visible_files:
            # 使用 Windows attrib 指令設為隱藏 (+h)
            os.system(f'attrib +h "{item}"')
    
    print("[SUCCESS] System items are now hidden.")

    print("\n" + "=" * 60)
    print(f"  [DONE] Packaging completed successfully!")
    print(f"  Path: {dest_dir}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"\n[ERROR] Packaging failed: {e}")
    os.system("pause")
