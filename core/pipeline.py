"""
pipeline.py
會議記錄全自動化流程：MP3 / .txt → HTML 會議記錄 + Word 檔
"""

import sys
import re
import json
import textwrap
from pathlib import Path
from datetime import datetime
from .shared import (
    get_key_pool, require_api_key, load_glossary, apply_glossary,
    pick_audio_or_text_file, gemini_call_with_retry, extract_json,
    MODEL_AUDIO, MODEL_TEXT, CORE_DIR
)
from .transcribe_cloud import transcribe_audio
from .build_html import build_html
from .build_docx import build_docx
from .html_to_pdf import html_to_pdf


# ── 整理 Prompt ───────────────────────────────────────────────────────────────
DICT_PROMPT = textwrap.dedent("""\
你是一位資深專業會議記錄整理員，擅長從口語化的逐字稿中提煉出高品質、高密度的會議記錄。
請閱讀以下逐字稿，輸出一個 JSON 物件，包含兩個 key：summary 和 meeting。

═══════════════════════════════════════════
【summary 結構】— 用於首頁摘要卡片
═══════════════════════════════════════════
{
  "big_title": "MM-DD 會議名稱（例如 04-21 製造部門檢討會議）",
  "sub_title": "會議名稱（不含日期）",
  "objective": "目標：一句話說明本次會議的核心目的與預期成果",
  "badges": [],
  "problems": ["問題1（具體描述）", "問題2", "問題3", "問題4"],
  "problems_title": "根據會議內容填寫適合的標題，例如「本次會議重點議題」或「現行運營問題與挑戰」",
  "key_numbers": [
    {"value": "數值", "label": "說明", "unit": "單位", "red": false}
  ],
  "key_numbers_title": "若有財務數字填寫標題（如「財務測算」「成本分析」），無則設空字串",
  "solution_title": "核心結論或行動方向標題（如「唯一獲利路徑」「根本解決方案」），無則留空字串",
  "solution_quote": "從逐字稿中提取最關鍵的一句原話或金句，用引號包裹，無則留空",
  "solution_subs": ["支撐結論的具體行動方向1", "支撐點2", "支撐點3"],
  "themes": [
    {"title": "主題一", "points": ["重點A（含具體內容）", "重點B"]},
    {"title": "主題二", "points": ["重點C", "重點D"]},
    {"title": "主題三", "points": ["重點E", "重點F"]}
  ],
  "action_groups": [
    {"group": "負責人姓名或職稱", "items": ["具體待辦1", "具體待辦2"]}
  ]
}

═══════════════════════════════════════════
【meeting 結構】— 用於詳細會議紀要
═══════════════════════════════════════════
{
  "sections": [
    {
      "heading": "一、段落標題",
      "paras": ["完整敘述段落（保留原文中的具體案例、比喻、數據計算過程）..."],
      "bullets": [[1, "主要條列"], [2, "子項目（含具體細節）"]],
      "closing": "段落結語或空字串"
    }
  ],
  "action_items": [
    {
      "owner": "@負責人姓名或職稱",
      "items": ["[ ] 具體待辦事項（含動作描述與預期成果） - [TBD]"]
    }
  ]
}

═══════════════════════════════════════════
【重要規則】
═══════════════════════════════════════════

■ 基本格式：
- 全部用繁體中文
- 完整保留所有數字、金額、百分比、人名、職稱、專案名稱、公司名稱
- badges 一律設為空列表 []
- 只輸出 JSON，不要加任何說明文字

■ 內容深度（極為重要）：
- sections 至少 6~10 段，每段需深入展開，不可只用一兩句話帶過
- 每段的 paras 應包含 2~4 句完整敘述，保留逐字稿中的具體案例、比喻、數據與計算過程
- bullets 應使用多層級（level 1 為主項，level 2 為子項說明），每段至少 2~5 條
- 若逐字稿中有講者舉具體案例或做數學計算，必須完整保留在 paras 或 bullets 中

■ 數據面板（key_numbers）：
- 盡量從逐字稿中提取 2~4 個關鍵數字（如成本、金額、人數、天數、百分比等）
- 若有對比數據（如成本 vs 報價），用 red: true 標記虧損或負面數字
- 無財務數字時設為空列表 []

■ 主題卡片（themes）：
- 至少 3~6 個主題，每個主題至少 2~3 個重點
- 每個重點應為完整的一句話（15~40字），不要只寫關鍵字

■ Action Items（最重要！）：
- 仔細辨識逐字稿中出現的【每一位】人名、職稱、暱稱或代號
- 為每一位被提及的人分別建立一組 action_group 和 action_items
- 每人至少 1~4 條具體待辦，格式為「[ ] 具體動作描述 - [TBD]」
- 若會議中明確指派某人做某事，必須完整記錄
- 若有共同任務，可建立聯合負責人（如「阿群 & 勝哥（共同）」）
- 若有全體適用的事項，建立「@所有同仁」或「@全體」
- 若無法確定具體人名但知道職稱，使用職稱（如「@廠長」「@總務」）
- 寧可多列、不可遺漏！action_items 是會議記錄最核心的產出

■ solution 區塊：
- solution_title 無明確結論時設為空字串
- solution_quote 應盡量從逐字稿中找出講者說的原話作為金句
- solution_subs 至少 2~3 條支撐點

逐字稿如下：
""")


def transcript_to_dicts(transcript: str) -> tuple:
    """逐字稿 → SUMMARY + MEETING dict"""
    print("[AI] Gemini 整理逐字稿中...")
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            resp = gemini_call_with_retry(MODEL_TEXT, DICT_PROMPT + transcript, json_mode=True)
            raw = resp.text.strip()
            data = extract_json(raw)
            break  # 成功解析則跳出迴圈
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"[WARN] JSON 格式錯誤，重新生成中（第 {attempt + 1} 次重試）...")
                continue
            else:
                debug_path = CORE_DIR / "_gemini_raw_response.txt"
                if 'raw' in locals():
                    debug_path.write_text(raw, encoding='utf-8')
                print(f"[ERR] JSON 解析失敗：{e}")
                print(f"   原始回傳已儲存至：{debug_path}")
                raise

    summary = data["summary"]
    meeting = data["meeting"]

    # bullets 格式統一轉成 list of tuples
    for sec in meeting.get("sections", []):
        bullets = sec.get("bullets", [])
        fixed = []
        for b in bullets:
            if isinstance(b, (list, tuple)) and len(b) == 2:
                fixed.append((int(b[0]), str(b[1])))
            elif isinstance(b, dict):
                fixed.append((int(b.get("level", 1)), str(b.get("text", ""))))
        sec["bullets"] = fixed

    print("[OK] 整理完成")
    return summary, meeting


def run(file_path=None):
    """全自動會議記錄主流程
    Args:
        file_path: 可選，直接指定輸入檔案路徑（拖曳模式）
    """
    print("\n" + "=" * 50)
    print("  📋 全自動會議記錄")
    print("=" * 50)

    if not require_api_key():
        return

    pool     = get_key_pool()
    glossary = load_glossary()

    # 選擇輸入檔（若已指定則跳過選擇視窗）
    if file_path:
        input_file = Path(file_path)
        if not input_file.exists():
            print(f"[ERR] 找不到檔案：{file_path}")
            return
    else:
        print("\n[DIR] 請選擇輸入檔案（MP3 錄音或 TXT 逐字稿）...")
        input_file = pick_audio_or_text_file()
        if not input_file:
            print("[ERR] 未選擇檔案，返回主選單。")
            return
    print(f"[OK] 已選擇：{input_file}")

    output_dir = input_file.parent

    # Step 1：音訊轉逐字稿
    if input_file.suffix.lower() in ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac'):
        _pool = get_key_pool()
        print(f"\n── Step 1：音訊 → 逐字稿 ── [使用 Key {_pool.index + 1}/{len(_pool.keys)}]")
        transcript = transcribe_audio(input_file, glossary)
        txt_path = output_dir / (input_file.stem + ".txt")
        txt_path.write_text(transcript, encoding='utf-8')
        print(f"[SAVE] 逐字稿已儲存：{txt_path}")
    elif input_file.suffix.lower() == '.txt':
        print("\n── Step 1：讀取逐字稿 ──")
        transcript = input_file.read_text(encoding='utf-8')
        if glossary:
            transcript = apply_glossary(transcript, glossary)
            print(f"[OK] 套用對照表 {len(glossary)} 條")
        print(f"[OK] 讀取完成（{len(transcript):,} 字）")
    else:
        print(f"[ERR] 不支援的檔案格式：{input_file.suffix}")
        return

    # Step 2：逐字稿 → dicts
    _pool = get_key_pool()
    print(f"\n── Step 2：整理會議記錄 ── [使用 Key {_pool.index + 1}/{len(_pool.keys)}]")
    summary, meeting = transcript_to_dicts(transcript)

    # 取標題作為檔名
    title = summary.get("sub_title", "會議記錄").replace("/", "_").replace("\\", "_")[:30]
    today = datetime.now().strftime("%Y-%m-%d")
    stem = f"{today}_{title}"

    # Step 3：儲存資料檔（供後續重新產出使用）【已停用，如需啟用請移除 # 號】
    # print("\n── Step 3：儲存資料檔 ──")
    # json_filename = f"{stem}_data.json"
    # json_path = output_dir / json_filename
    # data = {"summary": summary, "meeting": meeting}
    # json_path.write_text(
    #     json.dumps(data, ensure_ascii=False, indent=2),
    #     encoding='utf-8'
    # )
    # print(f"[OK] 資料檔已儲存：{json_path}")

    # Step 4：產出 HTML（中介檔，供 PDF 使用，不另存通知）
    html_filename = f"{stem}.html"
    html_path = output_dir / html_filename
    build_html(summary, meeting, str(html_path))

    # Step 5：產出 Word（詳細內文，方便編輯）【已停用，如需啟用請移除 # 號】
    # print("\n── Step 5：產出 Word ──")
    # docx_filename = f"{stem}.docx"
    # docx_path = output_dir / docx_filename
    # build_docx(summary, meeting, str(docx_path))

    # Step 5：嘗試轉 PDF，完成後刪除中介 HTML
    print("\n── Step 5：嘗試轉 PDF ──")
    html_to_pdf(str(html_path))
    if html_path.exists():
        html_path.unlink()
        print(f"[OK] 已刪除中介 HTML：{html_path.name}")

    print("\n" + "=" * 50)
    print(f"  ✅ 完成！輸出資料夾：{output_dir}")
    print(f"  🖨️  PDF 會議記錄：{stem}.pdf")
    print("=" * 50)

