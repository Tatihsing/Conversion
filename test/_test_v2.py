"""測試：動態積木式渲染 (build_html_v2) - 快取 Pass 1 結果，只迭代 Pass 2"""
import sys, os, json
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

# 路徑
txt_path = Path(r"D:\錄音檔\meeting-auto\test\c1206bd9c32d06c80b82f4c449bea90f.txt")
cache_path = txt_path.parent / "_pass1_cache.json"

# ── Pass 1：使用快取（如果存在就跳過，避免每次結果不同）──
if cache_path.exists():
    print(f"[CACHE] 使用快取的 Pass 1 結果：{cache_path.name}")
    with open(cache_path, 'r', encoding='utf-8') as f:
        cached = json.load(f)
    summary = cached["summary"]
    meeting = cached["meeting"]
else:
    # 讀取逐字稿
    transcript = txt_path.read_text(encoding='utf-8')
    if glossary:
        transcript = apply_glossary(transcript, glossary)
    print(f"[OK] 逐字稿 {len(transcript):,} 字")

    print("\n── Pass 1：AI 提煉內容 ──")
    summary, meeting = transcript_to_dicts(transcript)

    # 儲存快取
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump({"summary": summary, "meeting": meeting}, f, ensure_ascii=False, indent=2)
    print(f"[CACHE] Pass 1 結果已快取：{cache_path.name}")

# ── Pass 2：AI 排版組裝 HTML（每次都重跑，用來迭代排版品質）──
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
print(f"\n💡 提示：如需重新產生 Pass 1 內容，請刪除 test\\_pass1_cache.json")
