"""
html_to_pdf.py
用本機 Chrome headless 將 HTML 會議記錄轉成 PDF
"""

import sys
import os
import subprocess


# Chrome 可能的安裝路徑（Windows）
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
]


def find_chrome():
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ["chrome", "google-chrome", "chromium-browser", "chromium"]:
        try:
            result = subprocess.run(
                ["where" if os.name == "nt" else "which", name],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0]
        except Exception:
            pass
    return None


def html_to_pdf(html_path, pdf_path=None):
    html_path = os.path.abspath(html_path)
    if not os.path.exists(html_path):
        print(f"[ERR] 找不到 HTML 檔案：{html_path}")
        return False

    if pdf_path is None:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    chrome = find_chrome()
    if not chrome:
        print("[WARN] 找不到 Chrome，跳過 PDF 轉換")
        print("       請用 Chrome 開啟 HTML 後 Ctrl+P 手動轉換")
        return False

    print(f"[..] Chrome 轉 PDF 中...")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-extensions",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",   # Chrome < 112
        "--no-pdf-header-footer",     # Chrome >= 112
        f"file:///{html_path.replace(os.sep, '/')}",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.exists(pdf_path):
            size_kb = os.path.getsize(pdf_path) // 1024
            print(f"[OK] PDF 已儲存：{pdf_path}（{size_kb} KB）")
            return True
        else:
            print(f"[WARN] PDF 轉換失敗，請手動用 Chrome 開啟 HTML 列印")
            return False
    except Exception as e:
        print(f"[WARN] PDF 轉換失敗：{e}")
        return False
