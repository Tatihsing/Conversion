"""測試：動態積木式渲染 (build_html_v2) - 使用現有逐字稿"""
import sys, os
sys.path.insert(0, r"D:\錄音檔\meeting-auto")
os.chdir(r"D:\錄音檔\meeting-auto")

from core.shared import get_key_pool, load_glossary, apply_glossary
from core.pipeline import transcript_to_dicts
from core.build_html_v2 import build_html_v2
from core.html_to_pdf import html_to_pdf
from pathlib import Path
from datetime import datetime

# 初始化
pool = get_key_pool()
glossary = load_glossary()

# 讀取逐字稿
txt_path = Path(r"D:\錄音檔\meeting-auto\test\c1206bd9c32d06c80b82f4c449bea90f.txt")
transcript = txt_path.read_text(encoding='utf-8')
if glossary:
    transcript = apply_glossary(transcript, glossary)
print(f"[OK] 逐字稿 {len(transcript):,} 字")

# Pass 1：逐字稿 → dicts
print("\n── Pass 1：AI 提煉內容 ──")
summary, meeting = transcript_to_dicts(transcript)

# Pass 2：AI 排版組裝 HTML
print("\n── Pass 2：AI 排版設計師 ──")
title = summary.get("sub_title", "會議記錄").replace("/", "_").replace("\\", "_")[:30]
today = datetime.now().strftime("%Y-%m-%d")
stem = f"{today}_{title}"

html_path = txt_path.parent / f"{stem}_v2.html"
build_html_v2(summary, meeting, str(html_path))

# 轉 PDF
print("\n── 轉 PDF ──")
pdf_path = txt_path.parent / f"{stem}_v2.pdf"
html_to_pdf(str(html_path), str(pdf_path))

print(f"\n✅ 完成！請比對：")
print(f"   黃金標準：test\\becker.pdf")
print(f"   新版產出：test\\{stem}_v2.pdf")
