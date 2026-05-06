"""測試：v3 程式碼控制排版，使用 Pass 1 快取"""
import sys, os, json
sys.path.insert(0, r"D:\錄音檔\meeting-auto")
os.chdir(r"D:\錄音檔\meeting-auto")

from core.build_html_v3 import build_html_v3
from core.html_to_pdf import html_to_pdf
from pathlib import Path
from datetime import datetime

cache_path = Path(r"D:\錄音檔\meeting-auto\test\_pass1_cache.json")
with open(cache_path, 'r', encoding='utf-8') as f:
    cached = json.load(f)
summary = cached["summary"]
meeting = cached["meeting"]
print(f"[CACHE] 使用 Pass 1 快取：{cache_path.name}")

title = summary.get("sub_title", "會議記錄").replace("/", "_")[:30]
today = datetime.now().strftime("%Y-%m-%d")
stem = f"{today}_{title}_v3"

html_path = cache_path.parent / f"{stem}.html"
build_html_v3(summary, meeting, str(html_path))

print("\n── 轉 PDF ──")
pdf_path = cache_path.parent / f"{stem}.pdf"
html_to_pdf(str(html_path), str(pdf_path))

print(f"\n✅ 完成！")
print(f"   黃金標準：test\\becker.pdf")
print(f"   v3 產出：test\\{stem}.pdf")
