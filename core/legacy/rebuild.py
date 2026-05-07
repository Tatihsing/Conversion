"""
rebuild.py
從 _data.json 重新產生 HTML + Word + PDF（不需重新呼叫 API）

使用情境：
  1. 修改 _data.json 的內容後，重新產出 HTML 和 PDF
  2. 只需要重新轉 PDF（HTML 已存在）
  3. 更新 glossary 後重新套用並產出
"""

import json
from pathlib import Path
from ..shared import pick_file, load_glossary, fix_deep
from .build_html import build_html
from ..build_docx import build_docx
from ..html_to_pdf import html_to_pdf


def pick_json_file():
    return pick_file(
        title="選擇資料檔（_data.json）",
        filetypes=[
            ("資料檔", "*_data.json"),
            ("JSON 檔案", "*.json"),
            ("所有檔案", "*.*"),
        ]
    )


def pick_html_file():
    return pick_file(
        title="選擇 HTML 會議記錄",
        filetypes=[
            ("HTML 檔案", "*.html"),
            ("所有檔案", "*.*"),
        ]
    )


def _normalize_bullets(meeting: dict) -> dict:
    """確保 bullets 格式正確（list of tuples）"""
    for sec in meeting.get("sections", []):
        bullets = sec.get("bullets", [])
        fixed = []
        for b in bullets:
            if isinstance(b, (list, tuple)) and len(b) == 2:
                fixed.append((int(b[0]), str(b[1])))
            elif isinstance(b, dict):
                fixed.append((int(b.get("level", 1)), str(b.get("text", ""))))
        sec["bullets"] = fixed
    return meeting


def run():
    """重新產生主流程"""
    print("\n" + "=" * 50)
    print("  🔄 重新產生 HTML + Word + PDF")
    print("=" * 50)
    print()
    print("  請選擇操作：")
    print()
    print("  [1]  從 _data.json 重新產生  （修改資料後使用）")
    print("  [2]  只重新轉 PDF            （已有 HTML，只需要 PDF）")
    print()
    print("  [B]  返回")
    print()
    choice = input("  請輸入數字：").strip().upper()

    if choice == "B":
        return

    elif choice == "1":
        _rebuild_from_json()

    elif choice == "2":
        _pdf_only()

    else:
        print("\n  [!] 無效選項")


def _rebuild_from_json():
    """從 _data.json 讀取資料，重新產生 HTML + Word + PDF（選單版）"""
    print("\n[DIR] 請選擇資料檔（*_data.json）...")
    json_file = pick_json_file()
    if not json_file:
        print("[ERR] 未選擇檔案，返回。")
        return
    _rebuild_from_json_path(str(json_file))


def _rebuild_from_json_path(json_path: str):
    """從 _data.json 讀取資料，重新產生 HTML + Word + PDF（拖曳/直接呼叫版）"""
    json_file = Path(json_path)

    # 讀取 JSON
    try:
        data = json.loads(json_file.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[ERR] 讀取 JSON 失敗：{e}")
        return

    summary = data.get("summary", {})
    meeting = data.get("meeting", {})

    if not summary or not meeting:
        print("[ERR] JSON 格式錯誤，缺少 summary 或 meeting")
        return

    # 正規化 bullets 格式
    meeting = _normalize_bullets(meeting)

    # 是否重新套用 glossary
    apply_gl = input("\n  是否重新套用 glossary 對照表？(Y/N，預設 N)：").strip().upper()
    if apply_gl == "Y":
        glossary = load_glossary()
        if glossary:
            summary = fix_deep(summary, glossary)
            meeting = fix_deep(meeting, glossary)
            print(f"[OK] 套用對照表 {len(glossary)} 條")

    # 輸出到同一資料夾，同名（覆蓋原本的）
    output_dir = json_file.parent
    stem = json_file.name.replace("_data.json", "")
    if not stem:
        stem = json_file.stem

    html_path = output_dir / f"{stem}.html"
    docx_path = output_dir / f"{stem}.docx"

    print(f"\n[DIR] 輸出資料夾：{output_dir}")

    # 產出 HTML
    print("\n── 產出 HTML ──")
    build_html(summary, meeting, str(html_path))

    # 產出 Word
    print("\n── 產出 Word ──")
    build_docx(summary, meeting, str(docx_path))

    # 轉 PDF
    print("\n── 嘗試轉 PDF ──")
    html_to_pdf(str(html_path))

    print("\n" + "=" * 50)
    print(f"  ✅ 重新產生完成！")
    print(f"  📄 HTML：{html_path.name}")
    print(f"  📝 Word：{docx_path.name}")
    print("=" * 50)


def _pdf_only():
    """只把現有 HTML 轉成 PDF"""
    print("\n[DIR] 請選擇 HTML 會議記錄...")
    html_file = pick_html_file()
    if not html_file:
        print("[ERR] 未選擇檔案，返回。")
        return

    print(f"[OK] 已選擇：{html_file}")
    print("\n── 轉換 PDF ──")
    html_to_pdf(str(html_file))

    pdf_path = html_file.with_suffix(".pdf")
    if pdf_path.exists():
        print("\n" + "=" * 50)
        print(f"  ✅ PDF 轉換完成：{pdf_path.name}")
        print("=" * 50)
