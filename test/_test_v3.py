"""測試：v3 程式碼控制排版 — 有快取就用，沒快取就重跑 Pass 1"""
import sys, os, json
sys.path.insert(0, r"D:\錄音檔\meeting-auto")
os.chdir(r"D:\錄音檔\meeting-auto")

from core.shared import get_key_pool, load_glossary, apply_glossary
from core.pipeline import transcript_to_dicts, get_recording_date
from core.build_html_v3 import build_html_v3
from core.html_to_pdf import html_to_pdf
from pathlib import Path
from datetime import datetime

# 初始化
pool = get_key_pool()
glossary = load_glossary()

# 路徑
txt_path = Path(r"D:\錄音檔\meeting-auto\test\c1206bd9c32d06c80b82f4c449bea90f.txt")
cache_path = txt_path.parent / "_pass1_cache.json"

# ── Pass 1：有快取就用，避免重複 API 費用 ──
if cache_path.exists():
    print(f"[CACHE] 使用快取的 Pass 1 結果：{cache_path.name}")
    with open(cache_path, 'r', encoding='utf-8') as f:
        cached = json.load(f)
    summary = cached["summary"]
    meeting = cached["meeting"]
else:
    transcript = txt_path.read_text(encoding='utf-8')
    if glossary:
        transcript = apply_glossary(transcript, glossary)
    print(f"[OK] 逐字稿 {len(transcript):,} 字")

    # 統一用 get_recording_date（檔名 → 同名音訊 mtime → 檔案 mtime）
    recording_date = get_recording_date(txt_path)

    print("\n── Pass 1：AI 提煉內容（新 Prompt）──")
    summary, meeting = transcript_to_dicts(transcript, recording_date=recording_date)

    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump({"summary": summary, "meeting": meeting}, f, ensure_ascii=False, indent=2)
    print(f"[CACHE] Pass 1 結果已快取：{cache_path.name}")


# 預覽關鍵欄位
print(f"\n── 本次 Pass 1 結果預覽 ──")
print(f"  big_title:  {summary.get('big_title','')}")
print(f"  key_numbers: {len(summary.get('key_numbers',[]))} 個")
for n in summary.get('key_numbers', []):
    print(f"    {n.get('value')} {n.get('unit')} — {n.get('label')} (red={n.get('red')})")
print(f"  action_groups: {len(summary.get('action_groups',[]))} 組")
for g in summary.get('action_groups', []):
    print(f"    {g['group']}: {len(g.get('items',[]))} 項")
print(f"  sections: {len(meeting.get('sections',[]))} 段")

# ── 產出 HTML → PDF ──
title = summary.get("sub_title", "會議記錄").replace("/", "_").replace("\\", "_")[:30]
today = datetime.now().strftime("%Y-%m-%d")
stem = f"{today}_{title}_v3"

html_path = txt_path.parent / f"{stem}.html"
build_html_v3(summary, meeting, str(html_path))

print("\n── 轉 PDF ──")
pdf_path = txt_path.parent / f"{stem}.pdf"
html_to_pdf(str(html_path), str(pdf_path))

print(f"\n✅ 完成！")
print(f"   黃金標準：test\\becker.pdf")
print(f"   v3 產出：test\\{stem}.pdf")
print(f"\n💡 提示：刪除 test\\_pass1_cache.json 可強制重新執行 Pass 1")
