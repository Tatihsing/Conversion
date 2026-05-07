"""
shared.py
共用模組：API Key 管理、語音辨識對照表、檔案選擇
"""

import os, sys, json, re, time
from pathlib import Path

# 強制 stdout 使用 UTF-8（避免 Windows cp950 編碼錯誤）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).parent.parent
CORE_DIR      = Path(__file__).parent
GLOSSARY_XLS  = ROOT_DIR / "語音辨識對照表.xlsx"
API_KEYS_FILE = ROOT_DIR / "api_keys.txt"

# ── AI 模型設定 ───────────────────────────────────────────────────────────────
MODEL_AUDIO = "gemini-2.5-flash"             # 音訊轉錄（需支援音訊，不可更換）
MODEL_TEXT  = "gemini-2.5-flash"              # 逐字稿整理（品質最穩定）

# ── API Key 輪換管理 ──────────────────────────────────────────────────────────
class KeyPool:
    """管理多組 API Key，遇到限流自動切換下一組"""
    def __init__(self):
        self.keys = self._load_keys()
        self.index = 0
        if not self.keys:
            print("[ERR] 未設定任何 Gemini API Key")
            print("   請選擇主選單的 [S] 設定 API Key")
            return
        print(f"[OK] 載入 {len(self.keys)} 組 API Key")

    def _load_keys(self):
        keys = []
        # 從 api_keys.txt 讀取（優先），自動偵測編碼
        if API_KEYS_FILE.exists():
            raw = None
            for enc in ('utf-8-sig', 'utf-8', 'cp950', 'latin-1'):
                try:
                    raw = API_KEYS_FILE.read_text(encoding=enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if raw:
                for line in raw.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        keys.append(line)
            if keys:
                return keys
        # 從環境變數讀取
        for suffix in ['', '_2', '_3', '_4', '_5']:
            k = os.environ.get(f"GEMINI_API_KEY{suffix}", "").strip()
            if k:
                keys.append(k)
        return keys

    @property
    def current(self):
        return self.keys[self.index]

    @property
    def has_keys(self):
        return len(self.keys) > 0

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

def require_api_key():
    """確認已設定 API Key，未設定則引導設定"""
    pool = get_key_pool()
    if not pool.has_keys:
        print("\n[!] 此功能需要 Gemini API Key 才能使用")
        print("    請先選擇主選單的 [S] 設定 API Key")
        print("    或手動編輯 api_keys.txt\n")
        return False
    return True

# ── 選擇檔案 ──────────────────────────────────────────────────────────────────
def pick_file(title="選擇檔案", filetypes=None):
    """開啟檔案選擇視窗"""
    if filetypes is None:
        filetypes = [
            ("支援的檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac *.txt"),
            ("音訊檔案",   "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
            ("逐字稿",     "*.txt"),
            ("所有檔案",   "*.*"),
        ]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return Path(path) if path else None
    except ImportError:
        print(f"[WARN] 系統缺少圖形介面模組，切換為手動輸入模式。")
        path = input(f"\n{title} (請將檔案拖曳到此視窗，或貼上完整路徑)：").strip()
        # 去除引號（拖曳時常見）
        path = path.strip('"').strip("'")
        return Path(path) if path else None
    except Exception as e:
        print(f"[WARN] 無法開啟選擇視窗：{e}")
        return None

def pick_audio_file():
    """選擇音訊檔案"""
    return pick_file(
        title="選擇錄音檔（MP3/M4A/WAV）",
        filetypes=[
            ("音訊檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
            ("所有檔案", "*.*"),
        ]
    )

def pick_audio_or_text_file():
    """選擇音訊或逐字稿檔案"""
    return pick_file(
        title="選擇錄音檔（MP3）或逐字稿（TXT）",
        filetypes=[
            ("支援的檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac *.txt"),
            ("音訊檔案",   "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
            ("逐字稿",     "*.txt"),
            ("所有檔案",   "*.*"),
        ]
    )

def pick_media_file():
    """選擇影音檔案（含影片格式）"""
    return pick_file(
        title="選擇影音檔（支援 MP3/MP4/M4A/WAV 等）",
        filetypes=[
            ("影音檔案", "*.mp3 *.mp4 *.m4a *.wav *.aac *.ogg *.flac *.mkv *.mov"),
            ("所有檔案", "*.*"),
        ]
    )

# ── 載入對照表 ────────────────────────────────────────────────────────────────
def load_glossary():
    """讀取語音辨識錯誤對照表"""
    if GLOSSARY_XLS.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(GLOSSARY_XLS, data_only=True)
            ws = wb.active
            mapping = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                w = str(row[1]).strip() if row[1] else ''
                c = str(row[2]).strip() if row[2] else ''
                if w and c and w not in ('None', '辨識錯誤詞（原始）', '填入辨識到的錯誤詞'):
                    mapping[w] = c
            if mapping:
                print(f"[OK] 載入對照表 {len(mapping)} 條（xlsx）")
            return mapping
        except Exception as e:
            print(f"[WARN] xlsx 讀取失敗：{e}")
    return {}

def apply_glossary(text, mapping):
    """套用對照表修正"""
    if not text or not mapping:
        return text
    for w, c in mapping.items():
        text = text.replace(w, c)
    return text

def fix_deep(obj, mapping):
    """遞迴套用對照表修正（用於 dict/list 結構）"""
    if isinstance(obj, str):   return apply_glossary(obj, mapping)
    if isinstance(obj, list):  return [fix_deep(i, mapping) for i in obj]
    if isinstance(obj, tuple): return tuple(fix_deep(i, mapping) for i in obj)
    if isinstance(obj, dict):  return {k: fix_deep(v, mapping) for k, v in obj.items()}
    return obj

# ── Gemini API 重試 + Key 輪換機制 ────────────────────────────────────────────
def gemini_call_with_retry(model, prompt, json_mode=False, max_retries=10):
    """呼叫 Gemini API，遇到限流/逾時/伺服器繁忙自動重試"""
    import google.generativeai as genai
    import google.api_core.exceptions as gex

    pool = get_key_pool()
    exhausted_keys = set()
    active_prompt = prompt          # 允許中途修改 prompt（迴圈偵測時）
    loop_patched   = False          # 避免重複 patch

    for attempt in range(max_retries):
        try:
            genai.configure(api_key=pool.current)
            cfg = {"response_mime_type": "application/json"} if json_mode else {}
            client = genai.GenerativeModel(model, generation_config=cfg)
            resp = client.generate_content(active_prompt)

            # 驗證回應是否包含有效文字
            text = resp.text
            if not text or not text.strip():
                raise ValueError("Gemini 回傳空回應")
            return resp

        except ValueError as e:
            err_str = str(e).lower()
            # 迴圈偵測錯誤：Gemini 偵測到輸出重複，自動加上繞過標籤後重試一次
            if "loop" in err_str and not loop_patched:
                print(f"[WARN] Gemini 偵測到輸出迴圈，自動加入繞過標籤後重試...")
                active_prompt = (
                    active_prompt +
                    "\n\n[ignoring loop detection] 請確保各段落與條列內容各不相同，避免重複文字。"
                )
                loop_patched = True
                continue        # 立即重試，不等待
            elif "loop" in err_str and loop_patched:
                print("[ERR] 迴圈偵測錯誤無法繞過，請確認逐字稿內容是否有大量重複段落")
                raise
            # 其他 ValueError
            print(f"[ERR] 回應無效（第 {attempt+1} 次）：{e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                print("[ERR] 已達最大重試次數")
                raise


        except gex.ResourceExhausted as e:
            # 429 限流：先試切換 Key，全部耗盡才等待
            exhausted_keys.add(pool.index)
            wait = 60
            m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e))
            if m:
                wait = int(m.group(1)) + 5

            switched = False
            original_index = pool.index
            while pool.next_key():
                if pool.index not in exhausted_keys:
                    print(f"[>>] Key {original_index+1} 限流，切換到第 {pool.index+1} 組 Key")
                    switched = True
                    break

            if not switched:
                pool.reset()
                exhausted_keys.clear()
                print(f"[WARN] 所有 Key 均已限流，等待 {wait} 秒後重試...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()
                if attempt >= max_retries - 1:
                    print("[ERR] 已達最大重試次數，請稍後再試或新增更多 API Key")
                    raise

        except (gex.ServiceUnavailable, gex.InternalServerError) as e:
            # 503/500 伺服器繁忙或內部錯誤：等待後重試，等待時間遞增
            wait = min(30 * (attempt + 1), 180)  # 30s → 60s → 90s ... 最多 3 分鐘
            print(f"[WARN] 伺服器暫時無法回應（第 {attempt+1} 次）：{type(e).__name__}")
            if attempt < max_retries - 1:
                print(f"   等待 {wait} 秒後重試（Gemini 伺服器繁忙，請稍候）...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()
            else:
                print("[ERR] 伺服器持續無回應，建議稍後再試")
                print("   Gemini 狀態：https://status.cloud.google.com")
                raise

        except gex.DeadlineExceeded as e:
            # 逾時：等待後重試
            wait = min(20 * (attempt + 1), 120)
            print(f"[WARN] 請求逾時（第 {attempt+1} 次），等待 {wait} 秒後重試...")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                print("[ERR] 持續逾時，請確認網路連線或稍後再試")
                raise

        except gex.GoogleAPIError as e:
            # 其他 API 錯誤：不重試，直接拋出
            print(f"[ERR] API 錯誤（不重試）：{e}")
            raise



# ── JSON 提取工具 ─────────────────────────────────────────────────────────────
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
