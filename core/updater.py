"""
core/updater.py
啟動時自動比對 GitHub 最新版本，提示或自動更新
- 不需要登入，使用 GitHub Public API
- 更新流程：Python 只負責下載並解壓至暫存資料夾，
  實際搬移由 啟動.bat 在 Python 完全結束後執行，
  徹底避免 Windows 檔案鎖定問題。
"""

import subprocess
import json
import urllib.request
import zipfile
import shutil
import tempfile
import os
import sys
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


def _get_remote_changelog() -> str:
    """透過 GitHub Raw 取得遠端最新的 changelog.txt"""
    url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/core/changelog.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "meeting-auto-updater", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return resp.read().decode('utf-8').strip()
    except Exception:
        pass
    return "（無更新內容說明）"


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


def _cleanup_old_updates():
    """清除之前更新留下的舊資料夾或備份檔"""
    import shutil
    try:
        for item in ROOT.iterdir():
            name = item.name
            if name.startswith("core_old_") or name.endswith(".old"):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        os.remove(item)
                    except Exception:
                        pass
    except Exception:
        pass


def _do_zip_download() -> bool:
    """
    下載最新版 ZIP 並解壓至根目錄下的 _update_staging/ 暫存資料夾。
    實際搬移交由 啟動.bat 在 Python 完全結束後執行。
    成功後以 exit code 2 退出，bat 偵測到後接手搬移並重啟。
    """
    zip_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
    zip_path = ROOT / "_update.zip"
    staging_dir = ROOT / "_update_staging"

    try:
        # 清除舊的暫存
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

        print("[INFO] 正在下載最新版本，請稍候...")
        urllib.request.urlretrieve(zip_url, zip_path)
        print("[INFO] 下載完成，正在解壓縮...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(staging_dir)

        # 確認解壓後的 core 資料夾存在
        extracted_core = staging_dir / f"{GITHUB_REPO}-{GITHUB_BRANCH}" / "core"
        if not extracted_core.exists():
            print("[ERR] 解壓縮後找不到 core 資料夾，更新中止。")
            return False

        print("[OK] 下載完成！程式即將關閉，由啟動程式接手套用更新...")
        return True

    except Exception as e:
        print(f"[ERR] 下載更新失敗：{e}")
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
    # 執行更新前先清理舊的備份
    _cleanup_old_updates()
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

    # 有新版本，詢問是否立即更新
    changelog = _get_remote_changelog()
    print(f"\n{'='*60}")
    print(f"  發現新版本！ v{local} -> v{remote}")
    print(f"{'='*60}")
    print(f"\n  更新內容：\n  --------------------------------------------------")
    for line in changelog.splitlines():
        print(f"  * {line}")
    print(f"  --------------------------------------------------")
    print(f"\n  立即更新？下載完成後程式會自動重啟套用。")
    print(f"  [Y] 立即更新   [N] 略過，稍後再說")
    print()

    try:
        choice = input("  請輸入選擇（Y/N）：").strip().upper()
    except Exception:
        choice = "N"

    if choice == "Y":
        success = _do_zip_download()
        if success:
            # exit code 2 = 通知 bat 接手搬移並重啟
            sys.exit(2)
        else:
            print("[WARN] 更新下載失敗，繼續使用目前版本。")

    return False


def get_version_string() -> str:
    """取得版本字串，用於顯示在啟動畫面"""
    return f"v{_get_local_version()}"
