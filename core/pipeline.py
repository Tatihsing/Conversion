"""
pipeline.py
會議記錄全自動化流程：MP3 / .txt → HTML 會議記錄 + Word 檔
"""

import sys
import re
import os
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
from .build_html_v3 import build_html_v3   # v3 程式碼控制排版（主要引擎）
from .build_html import build_html           # v1 保留作為備用
from .build_docx import build_docx
from .html_to_pdf import html_to_pdf


def extract_number_contexts(text: str, window: int = 100, min_value: int = 100) -> str:
    """
    前處理：從逐字稿中提取所有數字及前後文
    - window: 數字前後各取多少字
    - min_value: 排除小於此值的數字（避免拉圈無意義的小數字）
    回傳：格式化的數字上下文字串，用於注入 Prompt
    """
    # 找所有數字（含千分位逗號）
    pattern = re.compile(r'\d[\d,]*')
    seen_values = set()
    results = []

    for m in pattern.finditer(text):
        raw = m.group().replace(',', '')
        try:
            val = int(raw)
        except ValueError:
            continue
        if val < min_value:
            continue
        if val in seen_values:
            continue
        seen_values.add(val)

        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        ctx = text[start:end].replace('\n', ' ').strip()
        results.append(f'- {m.group()}：「...{ctx}...」')

    if not results:
        return ''

    header = (
        '\n[逐字稿數字上下文清單 — 請優先參考這些數字進行 key_numbers 提取]\n'
        '（下方為逐字稿中出現的所有重要數字及其前後文，每個數字獨立出現一次）\n'
    )
    return header + '\n'.join(results) + '\n\n'


def get_recording_date(file_path: Path) -> str:
    """
    取得錄音/逐字稿的日期，格式 MM-DD
    優先順序：
    1. 檔名中的日期（YYYYMMDD 或 YYYY-MM-DD）— 最可靠，代表使用者命名習慣
    2. 若是 .txt 且同目錄有同名音訊檔，用音訊檔的 mtime
    3. 退回使用該檔案的 mtime（錄音後通常不會更動 mtime）
    """
    stem = file_path.stem

    # 嘗試解析檔名中的日期
    # 支援：20260421、2026-04-21、2026_04_21、20260421_xxx 等
    patterns = [
        r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})',   # YYYY-MM-DD 或 YYYYMMDD
    ]
    for pat in patterns:
        m = re.search(pat, stem)
        if m:
            month, day = m.group(2), m.group(3)
            date_str = f'{month}-{day}'
            print(f'[INFO] 日期來源：檔名解析 → {date_str}')
            return date_str

    # 若是 TXT，尋找同目錄同名的音訊檔（比 txt 更接近錄音時間）
    audio_exts = ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac')
    if file_path.suffix.lower() == '.txt':
        for ext in audio_exts:
            audio_path = file_path.with_suffix(ext)
            if audio_path.exists():
                mtime = audio_path.stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime('%m-%d')
                print(f'[INFO] 日期來源：同名音訊檔 mtime ({audio_path.name}) → {date_str}')
                return date_str

    # 退回：使用輸入檔的 mtime
    mtime = file_path.stat().st_mtime
    date_str = datetime.fromtimestamp(mtime).strftime('%m-%d')
    print(f'[INFO] 日期來源：檔案 mtime ({file_path.name}) → {date_str}')
    return date_str


# ── 整理 Prompt ───────────────────────────────────────────────────────────────
DICT_PROMPT = textwrap.dedent("""\
你是一位資深專業會議記錄整理員，擅長從口語化逐字稿中提煉出高品質、高密度的會議記錄。
請閱讀以下逐字稿，輸出一個 JSON 物件，包含兩個 key：summary 和 meeting。

═══════════════════════════════════════════
【summary 結構】— 用於首頁摘要儀表板
═══════════════════════════════════════════
{
  "big_title": "MM-DD 會議名稱（從逐字稿內容推斷日期，例如 04-21 製造部門檢討會議）",
  "sub_title": "會議名稱（不含日期的簡短名稱）",
  "objective": "目標：一句話說明本次會議的核心目的（不超過50字）",
  "badges": [],

  "problems": ["問題1（15~35字，具體描述症狀而非現象）", "問題2", "問題3", "問題4"],
  "problems_title": "根據會議性質命名，如「現行運營問題與成本壓力」「本次檢討重點」「核心挑戰分析」",

  "key_numbers": [
    {"value": "數值（只填數字，如6462或-600）", "label": "說明此數字代表的洞察（如「每人每日全成本」「每日出差虧損」）", "unit": "元", "red": false}
  ],
  "key_numbers_title": "數字卡片標題（如「財務測算（每人/每日）」「成本效益分析」），無財務數字則設空字串",

  "solution_title": "核心結論或行動方向標題（如「唯一獲利路徑：效率躍升」），無則空字串",
  "solution_quote": "從逐字稿提取最有衝擊力的原話作為金句，加引號，無則空字串",
  "solution_subs": ["支撐結論的具體行動或原則1（15~30字）", "支撐點2", "支撐點3"],

  "themes": [
    {
      "title": "主題標題（如「跨職能整合與時程控管」「科技賦能：AI實務應用」）",
      "sub_heading": "若主題有一個核心子議題值得強調則填入（如「職能交叉：基本電配共通化」），否則空字串",
      "points": ["重點A（完整一句話，15~40字，含具體做法或數據）", "重點B", "重點C"],
      "numbered_points": ["若主題有明確的執行步驟或時間序列則填入，否則設為空列表"]
    }
  ],

  "action_groups": [
    {"group": "功能性職責分組（如「生產與品質管理」「外勤與訓練落實」「科技工具導入」）或個人姓名/職稱",
     "items": ["[ ] 具體待辦項目，若功能組則含負責人說明（如「廠長：嚴控品質，避免未洗酸即出貨」） - [TBD]"]}
  ]
}

═══════════════════════════════════════════
【meeting 結構】— 用於詳細會議紀要（絕對不可省略）
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

■ 數據面板（key_numbers）— 依語境決定是否加總與如何呈現：
- 選出 2~4 個「最能說明問題核心或決策依據」的關鍵數字
- 優先選擇：對比數字（成本 vs 收入）、結論性數字（虧損額、效益%）、決策依據數字
- 【語境推導授權】：若講者在逐字稿中逐一列出費用明細，且討論語氣明顯在分析「總成本壓力」
  或「整體負擔」，你應主動將這些明細加總，計算出結論性數字呈現（這是分析師的職責）
  例如：講者列出薪資+勞健退+差旅+油資等明細並討論「一個人出去一天要多少錢」，
  你應計算合計並以「每人每日全成本 X 元」呈現，而不是把每個明細拆開列出
- 【保守原則】：若講者只是隨口提及某個數字，無明顯加總意圖，則直接用該數字，不要強行加總
- 若計算出推導數字，在 label 中說明（如「每人每日全成本（薪資+差旅+油資合計）」）
- 數量控制：key_numbers 最多 4 個，優先選最具衝擊力的結論數字
- 【最高優先級】損益結論句型：若逐字稿中出現「收X付Y」「賠Z」「虧損Z」「成本X報價Y」等
  損益結論，這些是最重要的 key_numbers，必須優先提取：
  範例：「我們收6000，要付6600，每天每人賠600」→
    提取：{"value":"6,000","label":"每日業務報價","unit":"元"}
         {"value":"6,600","label":"每日實際成本","unit":"元"}
         {"value":"-600","label":"每人每日虧損","unit":"元","red":true}
  而不是去列個別費用明細（250日支、400補貼等）
- 【次要】若有全成本合計（如6,462）且明確說出，也應列入
- red: true 使用場景：
  * 虧損、赤字、負值（每日賠600 → -600，red:true）
  * 「現況偏低且需調整」的數字（現行250遠低於合理水準400，標現況250 red:true）
  * 講者用「賠」「虧」「不合理」「問題」語氣描述的數字
- 若有現況 vs 建議對比，建議值不標 red；現況明顯不足才標 red
- 無財務數字時設為空列表 []

■ 主題卡片（themes）— 適用任何會議類型：
- 3~6 個主題，涵蓋會議中的不同面向（問題面、解方面、執行面、組織面等）
- 每個主題 points 應為完整句子（15~40字），含具體做法或數據，不得只寫關鍵字
- sub_heading：主題有明確核心子議題才填，否則空字串
- numbered_points：主題內容有明確步驟或時序才填，否則空列表 []
- 會議類型示例（僅供參考，不限於此）：
  製造業檢討→「品質管控」「跨部門協作」「成本結構」；
  行銷會議→「市場分析」「活動執行」「預算配置」；
  技術回顧→「問題根因」「改善方案」「預防措施」

■ Action Items — 功能性分組優先：
- summary.action_groups：優先按「功能職責」分組（如「生產品質管理」「外勤訓練」「科技工具」）
  而非直接用人名；功能組的 items 需含負責人說明（如「廠長：嚴控品質...」）
- 若有明確個人任務且無法歸入功能組，才單獨建立該人的分組
- meeting.action_items：按個人建立，仔細辨識逐字稿中【每一位】被提及的人名、職稱、暱稱
- 每人至少 1~4 條，格式：「[ ] 具體待辦事項 - [TBD]」
- 若有共同任務，建立聯合負責人（如「阿群 & 勝哥（共同）」）
- 寧可多列、不可遺漏！action_items 是會議記錄最核心的產出

■ 詳細段落（meeting.sections）— 絕對不可省略：
- 必須至少 6~10 段，每段需深入展開，不可只用一兩句話帶過
- 每段的 paras 應包含 2~4 句完整敘述
- 必須保留逐字稿中的具體案例、比喻、數字計算過程（這是最重要的部分）
- bullets 使用多層級（level 1 主項，level 2 子項說明），每段至少 2~5 條
- 若逐字稿中有講者舉具體案例或做數學計算，必須完整保留在 paras 或 bullets 中
- closing 為段落的結論性一句話，不可省略

逐字稿如下：
""")


def transcript_to_dicts(transcript: str, recording_date: str = '') -> tuple:
    """逐字稿 → SUMMARY + MEETING dict
    Args:
        transcript: 逐字稿文字
        recording_date: 錄音/會議日期，格式 MM-DD（如 04-21），空字串表示由 AI 自行推斷
    """
    print("[AI] Gemini 整理逐字稿中...")

    # 若有確切日期，在 Prompt 開頭明確告知，避免 AI 猜測
    if recording_date:
        date_hint = f"【重要】本次會議的錄音日期為：{recording_date}。big_title 的日期前綴請直接使用此日期，不要另行推斷。\n\n"
    else:
        date_hint = ''

    # 注入數字上下文清單
    number_hint = extract_number_contexts(transcript)
    prompt = DICT_PROMPT + date_hint + number_hint + transcript

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            resp = gemini_call_with_retry(MODEL_TEXT, prompt, json_mode=True)
            raw = resp.text.strip()
            data = extract_json(raw)
            break
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

    # Step 2：逐字稿 → dicts（傳入錄音日期，避免 AI 猜測）
    _pool = get_key_pool()
    print(f"\n── Step 2：整理會議記錄 ── [使用 Key {_pool.index + 1}/{len(_pool.keys)}]")
    # 取得錄音日期（優先解析檔名 → 同名音訊 mtime → 檔案 mtime）
    recording_date = get_recording_date(input_file)
    summary, meeting = transcript_to_dicts(transcript, recording_date=recording_date)

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

    # Step 4：產出 HTML（中介檔，供 PDF 使用）— 使用 v3 程式碼控制排版引擎
    html_filename = f"{stem}.html"
    html_path = output_dir / html_filename
    try:
        build_html_v3(summary, meeting, str(html_path))
    except Exception as e:
        print(f"[WARN] v3 渲染失敗：{e}，備用 v1 引擎")
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

    # Step 6：執行雲端備份
    try:
        from core.gdrive import backup_to_drive
        pdf_file = output_dir / f"{stem}.pdf"
        txt_file = input_file if input_file.suffix.lower() == '.txt' else input_file.with_suffix('.txt')
        
        # 尋找原始音檔（如果是文字檔為輸入）
        audio_file = input_file
        if audio_file.suffix.lower() == '.txt':
            for ext in ['.m4a', '.mp3', '.wav']:
                candidate = audio_file.with_suffix(ext)
                if candidate.exists():
                    audio_file = candidate
                    break

        backup_to_drive(
            audio_path=str(audio_file) if audio_file.exists() else None,
            pdf_path=str(pdf_file) if pdf_file.exists() else None,
            html_path=None, # HTML 已被刪除，不備份
            txt_path=str(txt_file) if txt_file.exists() else None
        )
    except Exception as e:
        print(f"[ERR] 雲端備份發生錯誤：{e}")

    # Step 7：自動開啟 PDF 檔案
    try:
        pdf_file = output_dir / f"{stem}.pdf"
        if pdf_file.exists():
            import os
            os.startfile(str(pdf_file))
    except Exception as e:
        print(f"[WARN] 無法自動開啟 PDF：{e}")

