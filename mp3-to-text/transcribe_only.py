"""
transcribe_only.py
純語音轉文字稿工具：MP3 -> TXT
"""

import os, sys, json, re, time, subprocess
from pathlib import Path
from datetime import datetime

# 強制 stdout 使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR   = Path(__file__).parent
GLOSSARY_XLS = SCRIPT_DIR.parent / "glossary.xlsx"
GLOSSARY_JSON= SCRIPT_DIR.parent / "glossary.json"
API_KEYS_FILE= SCRIPT_DIR.parent / "api_keys.txt"   # 多組 key 設定檔

MODEL_AUDIO  = "gemini-2.5-flash"   # 音訊轉錄

class KeyPool:
    def __init__(self):
        self.keys = self._load_keys()
        self.index = 0
        if not self.keys:
            print("[ERR] 未設定任何 Gemini API Key")
            sys.exit(1)
        print(f"[OK] 載入 {len(self.keys)} 組 API Key")

    def _load_keys(self):
        keys = []
        if API_KEYS_FILE.exists():
            for line in API_KEYS_FILE.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    keys.append(line)
            if keys:
                return keys
        for suffix in ['', '_2', '_3', '_4', '_5']:
            k = os.environ.get(f"GEMINI_API_KEY{suffix}", "").strip()
            if k:
                keys.append(k)
        return keys

    @property
    def current(self):
        return self.keys[self.index]

    def next_key(self):
        self.index += 1
        if self.index >= len(self.keys):
            return False
        print(f"[>>] 切換到第 {self.index + 1} 組 API Key")
        return True

    def reset(self):
        self.index = 0

_key_pool: KeyPool = None

def get_key_pool() -> KeyPool:
    global _key_pool
    if _key_pool is None:
        _key_pool = KeyPool()
    return _key_pool

def pick_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="選擇錄音檔（MP3/M4A/WAV）",
            filetypes=[
                ("音訊檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
                ("所有檔案", "*.*"),
            ]
        )
        root.destroy()
        return Path(path) if path else None
    except Exception as e:
        print(f"[WARN]  無法開啟選擇視窗：{e}")
        return None

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
        except Exception:
            pass
    return {}

def apply_glossary(text, mapping):
    for w, c in mapping.items():
        text = text.replace(w, c)
    return text

def gemini_call_with_retry(model, prompt, max_retries=10):
    import google.generativeai as genai
    import google.api_core.exceptions as gex

    pool = get_key_pool()
    exhausted_keys = set()

    for attempt in range(max_retries):
        try:
            genai.configure(api_key=pool.current)
            client = genai.GenerativeModel(model)
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
            if m: wait = int(m.group(1)) + 5

            switched = False
            original_index = pool.index
            while pool.next_key():
                if pool.index not in exhausted_keys:
                    print(f"[>>] Key {original_index+1} 已達限流，切換到第 {pool.index+1} 組 Key")
                    switched = True
                    break

            if not switched:
                pool.reset()
                exhausted_keys.clear()
                print(f"[WARN]  所有 Key 均已限流，等待 {wait} 秒後重試...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()
                if attempt >= max_retries - 1: raise

        except gex.GoogleAPIError as e:
            print(f"[ERR] API 錯誤：{e}")
            raise

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

    print("[MIC]  轉錄中（依長度可能需要數分鐘）...")
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

def main():
    print("=" * 50)
    print("  音訊轉文字稿工具 (純轉錄)")
    print("=" * 50)

    pool = get_key_pool()
    glossary = load_glossary()

    print("\n[DIR] 請選擇錄音檔案...")
    input_file = pick_file()
    if not input_file:
        print("[ERR] 未選擇檔案，結束。")
        sys.exit(0)
    
    if input_file.suffix.lower() not in ('.mp3','.m4a','.wav','.aac','.ogg','.flac'):
        print(f"[ERR] 必須選擇音訊檔案，目前選擇的是：{input_file.suffix}")
        sys.exit(1)

    print(f"[OK] 已選擇：{input_file}")
    output_dir = input_file.parent

    print("\n── 執行語音轉文字 ──")
    transcript = transcribe_audio(input_file, pool.current, glossary)
    txt_path = output_dir / (input_file.stem + "_逐字稿.txt")
    txt_path.write_text(transcript, encoding='utf-8')
    
    print("\n" + "=" * 50)
    print(f"[SAVE] 逐字稿已儲存至：\n{txt_path}")
    print("=" * 50)
    input("\n按 Enter 關閉...")

if __name__ == "__main__":
    main()
