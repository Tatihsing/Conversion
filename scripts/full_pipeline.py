"""
full_pipeline.py
會議記錄全自動化流程：MP3 / .txt → HTML 會議記錄

流程：
  1. 選擇輸入檔案（MP3 或 .txt）
  2. 若為 MP3 → Gemini API 轉逐字稿
  3. Gemini API 整理逐字稿 → SUMMARY + MEETING dict
  4. build_html.py 產出 HTML
  5. html_to_pdf.py 嘗試用 Chrome 轉 PDF

需求：
  pip install google-generativeai openpyxl
  環境變數設定（支援多組輪換）：
    GEMINI_API_KEY=key1
    GEMINI_API_KEY_2=key2
    GEMINI_API_KEY_3=key3
  或在 api_keys.txt 中每行一個 key（更方便管理）
"""

import os, sys, json, re, time, subprocess, textwrap
from pathlib import Path
from datetime import datetime

# 強制 stdout 使用 UTF-8（避免 Windows cp950 編碼錯誤）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
BUILD_HTML   = SCRIPT_DIR / "build_html.py"
HTML_TO_PDF  = SCRIPT_DIR / "html_to_pdf.py"
GLOSSARY_XLS = SCRIPT_DIR.parent / "glossary.xlsx"
GLOSSARY_JSON= SCRIPT_DIR.parent / "glossary.json"
API_KEYS_FILE= SCRIPT_DIR.parent / "api_keys.txt"   # 多組 key 設定檔

MODEL_AUDIO  = "gemini-2.5-flash"   # 音訊轉錄
MODEL_TEXT   = "gemini-2.5-flash"   # 逐字稿整理

# ── API Key 輪換管理 ──────────────────────────────────────────────────────────
class KeyPool:
    """管理多組 API Key，遇到限流自動切換下一組"""
    def __init__(self):
        self.keys = self._load_keys()
        self.index = 0
        if not self.keys:
            print("[ERR] 未設定任何 Gemini API Key")
            print("   請執行 02_setup_api_key.bat，或在 api_keys.txt 中填入 Key")
            sys.exit(1)
        print(f"[OK] 載入 {len(self.keys)} 組 API Key")

    def _load_keys(self):
        keys = []
        # 從 api_keys.txt 讀取（優先）
        if API_KEYS_FILE.exists():
            for line in API_KEYS_FILE.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    keys.append(line)
            if keys:
                return keys
        # 從環境變數讀取 GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3 ...
        for suffix in ['', '_2', '_3', '_4', '_5']:
            k = os.environ.get(f"GEMINI_API_KEY{suffix}", "").strip()
            if k:
                keys.append(k)
        return keys

    @property
    def current(self):
        return self.keys[self.index]

    def next_key(self):
        """切換到下一組 key，全部用完回傳 False"""
        self.index += 1
        if self.index >= len(self.keys):
            return False
        print(f"[>>] 切換到第 {self.index + 1} 組 API Key")
        return True

    def reset(self):
        self.index = 0

# 全域 key pool（初始化後共用）
_key_pool: KeyPool = None

def get_key_pool() -> KeyPool:
    global _key_pool
    if _key_pool is None:
        _key_pool = KeyPool()
    return _key_pool

# ── 選擇檔案 ──────────────────────────────────────────────────────────────────
def pick_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="選擇錄音檔（MP3）或逐字稿（TXT）",
            filetypes=[
                ("支援的檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac *.txt"),
                ("音訊檔案",   "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
                ("逐字稿",     "*.txt"),
                ("所有檔案",   "*.*"),
            ]
        )
        root.destroy()
        return Path(path) if path else None
    except Exception as e:
        print(f"[WARN]  無法開啟選擇視窗：{e}")
        return None

# ── 載入對照表 ────────────────────────────────────────────────────────────────
def load_glossary():
    if GLOSSARY_XLS.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(GLOSSARY_XLS, data_only=True)
            ws = wb.active
            mapping = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                w = str(row[1]).strip() if row[1] else ''
                c = str(row[2]).strip() if row[2] else ''
                if w and c and w not in ('None','辨識錯誤詞（原始）','填入辨識到的錯誤詞'):
                    mapping[w] = c
            print(f"[OK] 載入對照表 {len(mapping)} 條（xlsx）")
            return mapping
        except Exception as e:
            print(f"[WARN]  xlsx 讀取失敗：{e}")
    if GLOSSARY_JSON.exists():
        with open(GLOSSARY_JSON, encoding='utf-8') as f:
            data = json.load(f)
        mapping = {}
        for k, v in data.items():
            if k.startswith('_'): continue
            if isinstance(v, dict): mapping.update(v)
            elif isinstance(v, str): mapping[k] = v
        print(f"[OK] 載入對照表 {len(mapping)} 條（json）")
        return mapping
    return {}

def apply_glossary(text, mapping):
    for w, c in mapping.items():
        text = text.replace(w, c)
    return text

# ── Gemini 重試 + Key 輪換機制 ────────────────────────────────────────────────
def make_client(model, json_mode=False):
    """建立 Gemini client，使用目前的 key"""
    import google.generativeai as genai
    pool = get_key_pool()
    genai.configure(api_key=pool.current)
    cfg = {"response_mime_type": "application/json"} if json_mode else {}
    return genai.GenerativeModel(model, generation_config=cfg)

def gemini_call_with_retry(model, prompt, json_mode=False, max_retries=10):
    """呼叫 Gemini API，遇到 429 先切換 key，全部用完再等待重試"""
    import google.generativeai as genai
    import google.api_core.exceptions as gex

    pool = get_key_pool()
    exhausted_keys = set()

    for attempt in range(max_retries):
        try:
            genai.configure(api_key=pool.current)
            cfg = {"response_mime_type": "application/json"} if json_mode else {}
            client = genai.GenerativeModel(model, generation_config=cfg)
            resp = client.generate_content(prompt)

            # 驗證回應是否包含有效文字（避免 response.text 拋出 ValueError）
            text = resp.text
            if not text or not text.strip():
                raise ValueError("Gemini 回傳空回應")
            return resp

        except ValueError as e:
            print(f"[ERR] 轉錄失敗（attempt {attempt+1}）：{e}")
            if attempt < max_retries - 1:
                wait = 5
                print(f"      等待 {wait} 秒後重試...")
                time.sleep(wait)
            else:
                print("[ERR] 已達最大重試次數")
                raise

        except gex.ResourceExhausted as e:
            exhausted_keys.add(pool.index)
            wait = 60
            m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e))
            if m:
                wait = int(m.group(1)) + 5

            # 嘗試切換到下一組 key
            switched = False
            original_index = pool.index
            while pool.next_key():
                if pool.index not in exhausted_keys:
                    print(f"[>>] Key {original_index+1} 已達限流，切換到第 {pool.index+1} 組 Key")
                    switched = True
                    break

            if not switched:
                # 所有 key 都用完，等待後重置
                pool.reset()
                exhausted_keys.clear()
                print(f"[WARN]  所有 Key 均已限流，等待 {wait} 秒後重試...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()
                if attempt >= max_retries - 1:
                    print("[ERR] 已達最大重試次數，請明天再試或新增更多 API Key")
                    raise

        except gex.GoogleAPIError as e:
            print(f"[ERR] API 錯誤：{e}")
            raise

# ── Step 1：MP3 → 逐字稿 ──────────────────────────────────────────────────────
def transcribe_audio(mp3_path: Path, api_key: str, glossary: dict) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    mime_map = {'.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav',
                '.aac':'audio/aac','.ogg':'audio/ogg','.flac':'audio/flac'}
    mime = mime_map.get(mp3_path.suffix.lower(), 'audio/mpeg')

    print(f"[UP]  上傳音訊（{mp3_path.stat().st_size/1024/1024:.1f} MB）...")
    audio_file = genai.upload_file(str(mp3_path), mime_type=mime)

    print("[..] 等待處理", end="", flush=True)
    while audio_file.state.name == "PROCESSING":
        time.sleep(3); audio_file = genai.get_file(audio_file.name); print(".", end="", flush=True)
    print()

    if audio_file.state.name != "ACTIVE":
        raise RuntimeError(f"音訊處理失敗：{audio_file.state.name}")

    print("[MIC]  轉錄中...")
    prompt_text = ("請將這段錄音完整轉成繁體中文逐字稿。"
                   "每個發言者換行，能辨識者標注姓名如「張經理：」。"
                   "不清楚的地方標 [?]。直接輸出逐字稿，不加任何說明。")
    resp = gemini_call_with_retry(MODEL_AUDIO, [prompt_text, audio_file])
    transcript = resp.text

    try: genai.delete_file(audio_file.name)
    except: pass

    if glossary:
        transcript = apply_glossary(transcript, glossary)
        print(f"[OK] 套用對照表 {len(glossary)} 條")

    print(f"[OK] 轉錄完成（{len(transcript):,} 字）")
    return transcript

# ── Step 2：逐字稿 → SUMMARY + MEETING dict ───────────────────────────────────
DICT_PROMPT = textwrap.dedent("""
你是一位專業會議記錄整理員。請閱讀以下逐字稿，輸出一個 JSON 物件，包含兩個 key：summary 和 meeting。

【summary 結構】
{
  "big_title": "MM-DD 會議名稱（例如 04-21 製造部門檢討會議）",
  "sub_title": "會議名稱（不含日期）",
  "objective": "目標：一句話說明本次會議目的",
  "badges": [],
  "problems": ["問題1", "問題2", "問題3"],
  "problems_title": "根據會議內容填寫適合的標題，例如「本次會議重點議題」",
  "key_numbers": [
    {"value": "數值", "label": "說明", "unit": "單位", "red": false}
  ],
  "key_numbers_title": "若有財務數字填寫標題，無則設空字串",
  "solution_title": "核心結論或行動方向標題，無明確結論則留空字串",
  "solution_quote": "最關鍵的一句話金句，無則留空",
  "solution_subs": ["支撐點1", "支撐點2"],
  "themes": [
    {"title": "主題一", "points": ["重點A", "重點B"]},
    {"title": "主題二", "points": ["重點C", "重點D"]},
    {"title": "主題三", "points": ["重點E", "重點F"]}
  ],
  "action_groups": [
    {"group": "負責人姓名", "items": ["具體待辦1", "具體待辦2"]}
  ]
}

【meeting 結構】
{
  "sections": [
    {
      "heading": "一、段落標題",
      "paras": ["完整敘述段落..."],
      "bullets": [[1, "主要條列"], [2, "子項目"]],
      "closing": "段落結語或空字串"
    }
  ],
  "action_items": [
    {
      "owner": "@負責人姓名",
      "items": ["具體待辦事項 - [TBD]"]
    }
  ]
}

規則：
- 全部用繁體中文
- 完整保留數字、金額、人名、專案名稱
- key_numbers 無財務數字時設為空列表 []
- solution_title 無明確結論時設為空字串
- badges 一律設為空列表 []
- sections 至少 4~6 段
- 只輸出 JSON，不要加任何說明文字

逐字稿如下：
""")

def extract_json(raw: str) -> dict:
    """從 Gemini 回傳的文字中提取第一個完整 JSON 物件"""
    raw = raw.strip()

    # 移除 markdown code block
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```\s*$', '', raw)
    raw = raw.strip()

    # 嘗試直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 找到第一個 { 到對應的最後一個 } 之間的內容
    start = raw.find('{')
    if start == -1:
        raise ValueError("回傳內容中找不到 JSON 物件")

    # 用括號計數找到對應的結尾
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(raw[start:], start):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                json_str = raw[start:i+1]
                return json.loads(json_str)

    raise ValueError("無法從回傳內容中提取完整 JSON")

def transcript_to_dicts(transcript: str, api_key: str = None) -> tuple:
    print("[AI] Gemini 整理逐字稿中...")
    resp = gemini_call_with_retry(MODEL_TEXT, DICT_PROMPT + transcript, json_mode=True)
    raw = resp.text.strip()

    try:
        data = extract_json(raw)
    except Exception as e:
        # 儲存原始回傳方便除錯
        debug_path = SCRIPT_DIR / "_gemini_raw_response.txt"
        debug_path.write_text(raw, encoding='utf-8')
        print(f"[ERR] JSON 解析失敗：{e}")
        print(f"   原始回傳已儲存至：{debug_path}")
        raise
    summary = data["summary"]
    meeting = data["meeting"]

    # bullets 可能是 [[1,"text"]] 或 [{"level":1,"text":"..."}]，統一轉成 list of tuples
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

# ── Step 3：產出 HTML ──────────────────────────────────────────────────────────
def build_output(summary: dict, meeting: dict, output_dir: Path, title: str):
    # 讀取 build_html.py 模板
    template = BUILD_HTML.read_text(encoding='utf-8')

    # 取得日期
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}_{title}.html"
    output_path = output_dir / filename

    # 替換 SUMMARY、MEETING、OUTPUT 三處
    s_json = json.dumps(summary, ensure_ascii=False, indent=4)
    m_json = json.dumps(meeting, ensure_ascii=False, indent=4)

    # 把 JSON 轉成 Python dict 語法（主要是 true/false → True/False）
    def json_to_py(s):
        s = re.sub(r'\btrue\b',  'True',  s)
        s = re.sub(r'\bfalse\b', 'False', s)
        s = re.sub(r'\bnull\b',  'None',  s)
        # bullets: [[1, "text"]] → [(1, "text")]
        s = re.sub(r'\[(\d+),\s*"', r'(\1, "', s)
        s = re.sub(r'(".*?")\](?=\s*[,\]])', r'\1)', s)
        return s

    new_summary = f"SUMMARY = {json_to_py(s_json)}"
    new_meeting = f"MEETING = {json_to_py(m_json)}"
    new_output  = f'OUTPUT = r"{output_path}"'

    # 替換模板中的 SUMMARY / MEETING / OUTPUT
    template = re.sub(r'SUMMARY\s*=\s*\{[^}]*\}', new_summary, template, count=1, flags=re.DOTALL)
    template = re.sub(r'MEETING\s*=\s*\{[^}]*\}', new_meeting, template, count=1, flags=re.DOTALL)
    template = re.sub(r'OUTPUT\s*=\s*"".*', new_output, template, count=1)

    # 寫入暫存 py 並執行
    tmp_py = SCRIPT_DIR / "_run_build.py"
    tmp_py.write_text(template, encoding='utf-8')

    print(f"[..] 產出 HTML：{output_path}")
    result = subprocess.run(
        [sys.executable, str(tmp_py)],
        capture_output=True,
        encoding='utf-8',
        errors='replace'
    )
    tmp_py.unlink(missing_ok=True)

    if result.returncode != 0:
        err = (result.stderr or '')[:500]
        print(f"[ERR] HTML 產出失敗：{err}")
        sys.exit(1)

    if result.stdout:
        print(result.stdout.strip())
    return output_path

# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  會議記錄全自動化流程")
    print("=" * 50)

    pool     = get_key_pool()   # 初始化 key pool（含多組輪換）
    glossary = load_glossary()

    # 選擇輸入檔
    print("\n[DIR] 請選擇輸入檔案（MP3 錄音或 TXT 逐字稿）...")
    input_file = pick_file()
    if not input_file:
        print("[ERR] 未選擇檔案，結束。")
        sys.exit(0)
    print(f"[OK] 已選擇：{input_file}")

    output_dir = input_file.parent

    # Step 1：音訊轉逐字稿
    if input_file.suffix.lower() in ('.mp3','.m4a','.wav','.aac','.ogg','.flac'):
        print("\n── Step 1：音訊 → 逐字稿 ──")
        transcript = transcribe_audio(input_file, pool.current, glossary)
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
        sys.exit(1)

    # Step 2：逐字稿 → dicts
    print("\n── Step 2：整理會議記錄 ──")
    summary, meeting = transcript_to_dicts(transcript)

    # 取標題作為檔名
    title = summary.get("sub_title", "會議記錄").replace("/","_").replace("\\","_")[:30]

    # Step 3：產出 HTML
    print("\n── Step 3：產出 HTML ──")
    html_path = build_output(summary, meeting, output_dir, title)

    # Step 4：嘗試轉 PDF
    print("\n── Step 4：嘗試轉 PDF ──")
    if HTML_TO_PDF.exists():
        result = subprocess.run(
            [sys.executable, str(HTML_TO_PDF), str(html_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print("[WARN]  PDF 轉換失敗，請用 Chrome 開啟 HTML 後 Ctrl+P 手動轉換")
    else:
        print("[WARN]  找不到 html_to_pdf.py，請手動轉換")

    print("\n" + "=" * 50)
    print(f"  完成！輸出資料夾：{output_dir}")
    print("=" * 50)
    input("\n按 Enter 關閉...")

if __name__ == "__main__":
    main()
