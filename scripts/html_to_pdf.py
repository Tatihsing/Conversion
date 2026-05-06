"""
html_to_pdf.py
用本機 Chrome headless 將 HTML 會議記錄轉成 PDF

用法：
  python html_to_pdf.py <input.html> [output.pdf]

需求：
  - Windows 已安裝 Google Chrome（預設路徑或 PATH 內）
  - 不需要安裝任何 Python 套件
"""

import sys
import os
import subprocess

# 強制 stdout 使用 UTF-8（避免 Windows cp950 編碼錯誤）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Chrome 可能的安裝路徑（Windows）──────────────────────────────────────────
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    # macOS / Linux fallback
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
]

def find_chrome():
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    # 嘗試從 PATH 找
    for name in ["chrome", "google-chrome", "chromium-browser", "chromium"]:
        try:
            result = subprocess.run(["where" if os.name == "nt" else "which", name],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0]
        except Exception:
            pass
    return None

def html_to_pdf(html_path, pdf_path=None):
    html_path = os.path.abspath(html_path)
    if not os.path.exists(html_path):
        print(f"❌ 找不到 HTML 檔案：{html_path}")
        sys.exit(1)

    if pdf_path is None:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    chrome = find_chrome()
    if not chrome:
        print("❌ 找不到 Chrome，請確認已安裝 Google Chrome")
        print("   或手動指定路徑，例如：")
        print(r'   set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe')
        sys.exit(1)

    print(f"✅ 找到 Chrome：{chrome}")
    print(f"📄 HTML：{html_path}")
    print(f"📄 PDF 輸出：{pdf_path}")

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-extensions",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        f"file:///{html_path.replace(os.sep, '/')}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode == 0 and os.path.exists(pdf_path):
        size_kb = os.path.getsize(pdf_path) // 1024
        print(f"✅ 完成！PDF 已儲存：{pdf_path}（{size_kb} KB）")
    else:
        print(f"❌ 轉換失敗（return code: {result.returncode}）")
        if result.stderr:
            print(f"   錯誤訊息：{result.stderr[:300]}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python html_to_pdf.py <input.html> [output.pdf]")
        print("範例：python html_to_pdf.py dashboard.html meeting.pdf")
        sys.exit(1)

    html_file = sys.argv[1]
    pdf_file  = sys.argv[2] if len(sys.argv) >= 3 else None
    html_to_pdf(html_file, pdf_file)
