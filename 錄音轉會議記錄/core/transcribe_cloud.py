"""
transcribe_cloud.py
雲端語音轉文字稿：使用 Gemini API
MP3/M4A/WAV → 繁體中文逐字稿
"""

import time
from pathlib import Path
from .shared import (
    get_key_pool, gemini_call_with_retry, load_glossary, apply_glossary,
    pick_audio_file, require_api_key, MODEL_AUDIO
)


def transcribe_audio(mp3_path: Path, glossary: dict, max_retries: int = 10) -> str:
    """上傳音訊到 Gemini API 進行轉錄（file 和 API call 綁定同一個 Key）"""
    import google.generativeai as genai
    import google.api_core.exceptions as gex

    pool = get_key_pool()
    exhausted_keys = set()

    mime_map = {
        '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.wav': 'audio/wav',
        '.aac': 'audio/aac',  '.ogg': 'audio/ogg',  '.flac': 'audio/flac'
    }
    mime = mime_map.get(mp3_path.suffix.lower(), 'audio/mpeg')
    prompt_text = (
        "請將這段錄音完整轉成繁體中文逐字稿。"
        "每個發言者換行，能辨識者標注姓名如「張經理：」。"
        "不清楚的地方標 [?]。直接輸出逐字稿，不加任何說明。"
    )

    audio_file = None

    for attempt in range(max_retries):
        try:
            # ── 每次嘗試都用目前的 Key 重新設定 + 上傳 ──
            genai.configure(api_key=pool.current)

            if not audio_file:
                print(f"[UP]  上傳音訊（{mp3_path.stat().st_size/1024/1024:.1f} MB）"
                      f"（Key {pool.index + 1}）...")
                audio_file = genai.upload_file(str(mp3_path), mime_type=mime)

                print("[..] 等待處理", end="", flush=True)
                while audio_file.state.name == "PROCESSING":
                    time.sleep(3)
                    audio_file = genai.get_file(audio_file.name)
                    print(".", end="", flush=True)
                print()

                if audio_file.state.name != "ACTIVE":
                    raise RuntimeError(f"音訊處理失敗：{audio_file.state.name}")

            print("[MIC] 轉錄中...")
            
            # 動態溫度：從 0.4 起步，避免 0.0~0.2 容易引發的無限迴圈當機
            current_temp = min(0.4 + (attempt * 0.2), 1.0)
            client = genai.GenerativeModel(MODEL_AUDIO, generation_config={"temperature": current_temp})
            
            resp = client.generate_content([prompt_text, audio_file], request_options={"timeout": 600})
            
            # 嘗試取得文字
            try:
                transcript = resp.text
            except ValueError as e:
                if "quick accessor" in str(e):
                    raise ValueError(f"Gemini 回傳異常空白 (Finish Reason 1)，將提高溫度重試 ({e})")
                raise

            if not transcript or not transcript.strip():
                raise ValueError("Gemini 回傳空回應")
                
            # 偵測「無限迴圈幻覺」：如果某句超過 20 字的話重複出現超過 5 次，代表 AI 卡死了
            import re
            # 找尋長度大於 20 的重複片段
            loop_match = re.search(r'(.{20,})\1{4,}', transcript)
            if loop_match or "the last time we talked about" in transcript.lower():
                raise ValueError("偵測到 AI 陷入無限重複的文字迴圈幻覺")

            # 成功，刪除上傳的檔案
            try:
                genai.delete_file(audio_file.name)
            except Exception:
                pass
            audio_file = None

            if glossary:
                transcript = apply_glossary(transcript, glossary)
                print(f"[OK] 套用對照表 {len(glossary)} 條")

            print(f"[OK] 轉錄完成（{len(transcript):,} 字）")
            return transcript

        except gex.ResourceExhausted as e:
            # 遇到限流：先刪除舊 Key 上傳的檔案，再切換 Key
            exhausted_keys.add(pool.index)
            if audio_file:
                try:
                    genai.delete_file(audio_file.name)
                    print(f"\n[DEL] 已刪除 Key {pool.index+1} 上的音訊檔")
                except Exception:
                    pass
                audio_file = None

            # 找下一個未限流的 Key
            switched = False
            while pool.next_key():
                if pool.index not in exhausted_keys:
                     print(f"[>>] 切換到第 {pool.index+1} 組 Key，重新上傳音訊...")
                     switched = True
                     break

            if not switched:
                # 所有 Key 都限流，等待後重置
                import re as _re
                wait = 60
                m = _re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e))
                if m:
                    wait = int(m.group(1)) + 5
                pool.reset()
                exhausted_keys.clear()
                print(f"[WARN] 所有 Key 均已限流，等待 {wait} 秒後重試...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()

        except gex.DeadlineExceeded as e:
            wait = min(30 * (attempt + 1), 120)
            print(f"[WARN] 請求逾時（檔案較大，第 {attempt+1} 次），等待 {wait} 秒後重試...")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise

        except (gex.ServiceUnavailable, gex.InternalServerError) as e:
            wait = min(30 * (attempt + 1), 120)
            print(f"[WARN] 伺服器繁忙（第 {attempt+1} 次），等待 {wait} 秒後重試...")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise

        except (RuntimeError, ValueError) as e:
            print(f"[ERR] 轉錄失敗（第 {attempt+1} 次）：{e}")
            if audio_file:
                try:
                    genai.delete_file(audio_file.name)
                except Exception:
                    pass
                audio_file = None
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise

    raise RuntimeError(f"轉錄失敗，已重試 {max_retries} 次")



def run():
    """純轉逐字稿主流程"""
    print("\n" + "=" * 50)
    print("  🎤 雲端語音轉文字稿（Gemini）")
    print("=" * 50)

    if not require_api_key():
        return

    glossary = load_glossary()

    print("\n[DIR] 請選擇錄音檔案...")
    input_file = pick_audio_file()
    if not input_file:
        print("[ERR] 未選擇檔案，返回主選單。")
        return

    if input_file.suffix.lower() not in ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac'):
        print(f"[ERR] 必須選擇音訊檔案，目前選擇的是：{input_file.suffix}")
        return

    print(f"[OK] 已選擇：{input_file}")

    print("\n── 執行語音轉文字 ──")
    transcript = transcribe_audio(input_file, glossary)
    txt_path = input_file.parent / (input_file.stem + "_逐字稿.txt")
    txt_path.write_text(transcript, encoding='utf-8')

    print("\n" + "=" * 50)
    print(f"[SAVE] 逐字稿已儲存至：")
    print(f"  {txt_path}")
    print("=" * 50)
