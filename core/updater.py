"""
core/updater.py
啟動時自動比對 GitHub 最新版本，提示或自動更新
- 不需要登入，使用 GitHub Public API
- 可攜版友善：有 git 則 git pull，無 git 則顯示下載連結
"""

import subprocess
import json
import urllib.request
import zipfile
import shutil
import tempfile
import os
from pathlib import Path

# ── GitHub 倉庫設定 ──────────────────────────────────────────────────────
GITHUB_OWNER  = "Tatihsing"
GITHUB_REPO   = "Conversion"
GITHUB_BRANCH = "main"
# ─────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent   # 專案根目錄


def _get_local_version() -> str:
    """讀取本機的 version.txt"""
    version_file = ROOT / "core" / "version.txt"
    try:
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "0.0.0"


def _get_remote_version() -> str:
    """透過 GitHub Raw 取得遠端最新的 version.txt"""
    url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/core/version.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "meeting-auto-updater", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return resp.read().decode('utf-8').strip()
    except Exception:
        pass
    return ""


def _has_git() -> bool:
    """確認 git 指令是否可用"""
    try:
        subprocess.check_output(["git", "--version"], capture_output=True, timeout=3)
        return True
    except Exception:
        return False


def _do_git_pull() -> bool:
    """執行 git pull，回傳是否成功"""
    try:
        result = subprocess.run(
            ["git", "pull", "origin", GITHUB_BRANCH],
            cwd=ROOT, capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"[OK] 更新完成！\n{result.stdout.strip()}")
            return True
        else:
            print(f"[ERR] git pull 失敗：{result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"[ERR] git pull 錯誤：{e}")
        return False


def _do_zip_update() -> bool:
    """無 git 環境下，下載 ZIP 並覆蓋更新 core 資料夾"""
    zip_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
    zip_path = ROOT / "update.zip"
    try:
        print("[INFO] 正在下載最新版本，請稍候...")
        urllib.request.urlretrieve(zip_url, zip_path)
        print("[INFO] 下載完成，正在套用更新...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # GitHub 壓縮檔解開後會有一個根目錄 (例如 Conversion-main)
            extracted_folder = os.path.join(temp_dir, f"{GITHUB_REPO}-{GITHUB_BRANCH}")
            source_core = os.path.join(extracted_folder, "core")
            target_core = ROOT / "core"
            
            if os.path.exists(source_core):
                # 覆蓋 core 資料夾
                shutil.copytree(source_core, target_core, dirs_exist_ok=True)
                
                # 順便更新外層腳本
                for file_name in ["start.bat", "啟動.bat", "README.md"]:
                    src_file = os.path.join(extracted_folder, file_name)
                    if os.path.exists(src_file):
                        shutil.copy2(src_file, ROOT / file_name)
                        
                print("[OK] 自動更新成功！請關閉並「重新啟動程式」以套用新版功能。")
                return True
            else:
                print("[ERR] 更新失敗：無法在下載的檔案中找到 core 資料夾。")
                return False
    except Exception as e:
        print(f"[ERR] ZIP 自動更新失敗：{e}")
        return False
    finally:
        if zip_path.exists():
            try:
                os.remove(zip_path)
            except Exception:
                pass


def check_for_updates(auto_update: bool = False, silent: bool = False) -> bool:
    """
    比對本機與遠端版本，有新版本時提示或自動更新

    Args:
        auto_update: True = 有更新直接 git pull（不詢問）
        silent: True = 版本相同時不印任何訊息

    Returns:
        True = 已是最新 / False = 有更新但未更新
    """
    # 若 GitHub 設定未填，直接略過
    if GITHUB_OWNER == "your-org":
        return True

    local  = _get_local_version()
    remote = _get_remote_version()

    if not remote:
        if not silent:
            print("[INFO] 無法連線至 GitHub 取得最新版本資訊")
        return True

    def _parse_version(v: str) -> tuple:
        try:
            return tuple(map(int, v.split('.')))
        except Exception:
            return (0, 0, 0)

    # 比較版本大小，若本機 >= 遠端，則視為最新（防止被舊版快取覆蓋降級）
    if _parse_version(local) >= _parse_version(remote):
        if not silent:
            print(f"[OK] 目前版本已是最新（v{local}）")
        return True

    # 有新版本
    print(f"\n{'='*50}")
    print(f"  🔔 發現新版本！")
    print(f"  目前版本：v{local}")
    print(f"  最新版本：v{remote}")
    print(f"{'='*50}")

    if auto_update:
        print("[AUTO] 自動更新中...")
        if _has_git():
            success = _do_git_pull()
        else:
            success = _do_zip_update()
        if success:
            import sys
            sys.exit(0)
        return False

    print("  輸入 Y 立即自動更新，或按 Enter 略過：", end="", flush=True)
    try:
        ans = input().strip().lower()
    except Exception:
        ans = ""
        
    if ans == "y":
        if _has_git():
            success = _do_git_pull()
        else:
            success = _do_zip_update()
        
        if success:
            import sys
            sys.exit(0)
    else:
        print(f"[INFO] 已略過更新。")

    return False


def get_version_string() -> str:
    """取得版本字串，用於顯示在啟動畫面"""
    return f"v{_get_local_version()}"
