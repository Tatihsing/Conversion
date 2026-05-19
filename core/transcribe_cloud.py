"""
transcribe_cloud.py
雲端語音轉文字稿：使用 Gemini API
MP3/M4A/WAV → 繁體中文逐字稿

功能：
- 自動偵測音訊時長，超過 25 分鐘自動切段（避免 API 逾時）
- ffmpeg 跨機器容錯：找不到時直接整段上傳（加長逾時）
- PROCESSING 等待上限，防止無限輪詢
"""

import re
import time
import json
import subprocess
import tempfile
from pathlib import Path
from .shared import (
    get_key_pool, load_glossary, apply_glossary,
    pick_audio_file, require_api_key, MODEL_AUDIO
)

CHUNK_THRESHOLD_MIN  = 25    # 超過此分鐘數才切段
CHUNK_THRESHOLD_MB   = 50    # 超過此 MB 也切段（應對高位元率短音訊）
CHUNK_SIZE_MIN       = 20    # 每段長度（分鐘）
PROCESSING_TIMEOUT   = 300   # PROCESSING 等待上限（秒）
API_TIMEOUT_SHORT    = 900   # < 25 分鐘音訊的 API 逾時（秒）
API_TIMEOUT_CHUNK    = 720   # 每段的 API 逾時（秒）


# ── ffmpeg 定位（跨機器容錯）────────────────────────────────────────────────

def _find_ffmpeg() -> tuple:
    """
    嘗試定位 ffmpeg / ffprobe 執行檔
    搜尋順序：
    1. 系統 PATH（最常見）
    2. Windows 常見安裝路徑
    3. 本專案 tools/ 目錄（可放入 portable 版）
    回傳：(ffmpeg_path, ffprobe_path) 或 (None, None)
    """
    import shutil
    import sys

    # 1. PATH
    ff  = shutil.which('ffmpeg')
    ffp = shutil.which('ffprobe')
    if ff and ffp:
        return ff, ffp

    # 2. Windows 常見安裝路徑
    win_paths = [
        r'C:\ffmpeg\bin',
        r'C:\Program Files\ffmpeg\bin',
        r'C:\Program Files (x86)\ffmpeg\bin',
    ]
    for d in win_paths:
        ff_candidate  = Path(d) / 'ffmpeg.exe'
        ffp_candidate = Path(d) / 'ffprobe.exe'
        if ff_candidate.exists() and ffp_candidate.exists():
            return str(ff_candidate), str(ffp_candidate)

    # 3. 本專案 tools/ 目錄（使用者可自行放 portable ffmpeg）
    project_root = Path(__file__).parent.parent
    tools_ff  = project_root / 'tools' / 'ffmpeg.exe'
    tools_ffp = project_root / 'tools' / 'ffprobe.exe'
    if tools_ff.exists() and tools_ffp.exists():
        return str(tools_ff), str(tools_ffp)

    return None, None


_FFMPEG, _FFPROBE = _find_ffmpeg()

if _FFMPEG:
    print(f"[INFO] ffmpeg 已就緒：{_FFMPEG}")
else:
    print("[WARN] 找不到 ffmpeg，長音訊（>25分鐘）將直接整段上傳（逾時風險較高）")


# ── 音訊工具函式 ────────────────────────────────────────────────────────────

def get_audio_duration(path: Path) -> float:
    """用 ffprobe 取得音訊時長（秒），找不到 ffprobe 時回傳 0"""
    if not _FFPROBE:
        return 0.0
    cmd = [_FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_format', str(path)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=30)
        info = json.loads(out)
        return float(info['format'].get('duration', 0))
    except Exception:
        return 0.0


def split_audio_chunks(src: Path, chunk_sec: int, tmp_dir: Path) -> list:
    """
    用 ffmpeg 將音訊切成指定長度的段落
    回傳：list of Path，若 ffmpeg 不可用則回傳空 list
    """
    if not _FFMPEG:
        return []

    pattern = str(tmp_dir / 'chunk_%03d.mp3')
    cmd = [
        _FFMPEG, '-y', '-i', str(src),
        '-f', 'segment',
        '-segment_time', str(chunk_sec),
        '-reset_timestamps', '1',
        '-c:a', 'libmp3lame',
        '-b:a', '64k',
        pattern
    ]
    try:
        # 由於加入重新編碼，將逾時放寬以應對較長音訊
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("[WARN] ffmpeg 切割逾時，退回整段模式")
        return []
    except subprocess.CalledProcessError as e:
        print(f"[WARN] ffmpeg 切割失敗：{e.stderr.decode(errors='replace')[:200]}，退回整段模式")
        return []

    return sorted(tmp_dir.glob('chunk_*.mp3'))


# ── 核心轉錄函式 ────────────────────────────────────────────────────────────

def _transcribe_single(mp3_path: Path, glossary: dict, max_retries: int = 10,
                       api_timeout: int = API_TIMEOUT_SHORT) -> str:
    """單段轉錄（內部使用）"""
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
        "如果這段錄音完全沒有人說話或只有環境噪音，請只輸出「（此段無語音）」。"
    )

    audio_file = None
    processing_start = None

    for attempt in range(max_retries):
        try:
            genai.configure(api_key=pool.current)

            if not audio_file:
                size_mb = mp3_path.stat().st_size / 1024 / 1024
                print(f"[UP]  上傳音訊（{size_mb:.1f} MB）（Key {pool.index + 1}）...")
                audio_file = genai.upload_file(str(mp3_path), mime_type=mime)

                print("[..] 等待處理", end="", flush=True)
                processing_start = time.time()
                while audio_file.state.name == "PROCESSING":
                    if time.time() - processing_start > PROCESSING_TIMEOUT:
                        raise RuntimeError(
                            f"PROCESSING 等待逾時（>{PROCESSING_TIMEOUT}秒），將重試"
                        )
                    time.sleep(3)
                    audio_file = genai.get_file(audio_file.name)
                    print(".", end="", flush=True)
                print()

                if audio_file.state.name != "ACTIVE":
                    raise RuntimeError(f"音訊處理失敗：{audio_file.state.name}")

            print("[MIC] 轉錄中...")
            current_temp = min(0.4 + (attempt * 0.2), 1.0)
            client = genai.GenerativeModel(MODEL_AUDIO, generation_config={"temperature": current_temp})
            resp = client.generate_content([prompt_text, audio_file], request_options={"timeout": api_timeout})

            try:
                transcript = resp.text
            except ValueError as e:
                # 處理 Gemini 判定無語音而直接 STOP 的情況
                if resp.candidates and (getattr(resp.candidates[0].finish_reason, "name", "") == "STOP" or resp.candidates[0].finish_reason == 1):
                    print("  [INFO] 此段音訊未辨識到語音，自動填入（此段無語音）")
                    transcript = "（此段無語音）"
                elif "quick accessor" in str(e):
                    raise ValueError(f"Gemini 回傳異常空白，將提高溫度重試（{e}）")
                else:
                    raise

            if not transcript or not transcript.strip():
                if resp.candidates and (getattr(resp.candidates[0].finish_reason, "name", "") == "STOP" or resp.candidates[0].finish_reason == 1):
                    print("  [INFO] 此段音訊未辨識到語音，自動填入（此段無語音）")
                    transcript = "（此段無語音）"
                else:
                    raise ValueError("Gemini 回傳空回應")

            # 偵測無限迴圈幻覺
            if re.search(r'(.{20,})\1{4,}', transcript):
                raise ValueError("偵測到 AI 陷入無限重複文字迴圈")

            # 清除上傳的檔案
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
            exhausted_keys.add(pool.index)
            if audio_file:
                try:
                    genai.delete_file(audio_file.name)
                    print(f"\n[DEL] 已刪除 Key {pool.index+1} 上的音訊檔")
                except Exception:
                    pass
                audio_file = None

            switched = False
            while pool.next_key():
                if pool.index not in exhausted_keys:
                    print(f"[>>] 切換到第 {pool.index+1} 組 Key，重新上傳音訊...")
                    switched = True
                    break

            if not switched:
                wait = 60
                m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e))
                if m:
                    wait = int(m.group(1)) + 5
                pool.reset()
                exhausted_keys.clear()
                print(f"[WARN] 所有 Key 均已限流，等待 {wait} 秒後重試...")
                for i in range(wait, 0, -5):
                    print(f"   剩餘 {i} 秒...", end='\r')
                    time.sleep(min(5, i))
                print()

        except gex.DeadlineExceeded:
            wait = min(30 * (attempt + 1), 120)
            print(f"[WARN] 請求逾時（第 {attempt+1} 次），等待 {wait} 秒後重試...")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise

        except (gex.ServiceUnavailable, gex.InternalServerError):
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

        except Exception as e:
            err_str = str(e).lower()
            # 捕捉 upload_file 拋出的 HttpError 或其他 API 錯誤
            if "403" in err_str or "leaked" in err_str or "permission denied" in err_str or "api_key_invalid" in err_str or "expired" in err_str:
                print(f"[ERR] API Key 權限錯誤或已失效：{e}")
                if audio_file:
                    try:
                        genai.delete_file(audio_file.name)
                    except Exception:
                        pass
                    audio_file = None
                    
                if pool.remove_current_key():
                    exhausted_keys.clear()
                    continue
                else:
                    print("[ERR] 所有可用的 API Key 均已失效，請更新 api_keys.txt")
                    raise
            
            print(f"[ERR] 未知系統或 API 錯誤：{e}")
            raise

    raise RuntimeError(f"轉錄失敗，已重試 {max_retries} 次")


def _transcribe_chunked(mp3_path: Path, glossary: dict, max_retries: int) -> str:
    """切段轉錄：分段轉錄後合併"""
    chunk_sec = CHUNK_SIZE_MIN * 60

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print(f"[CHUNK] 分割音訊中...")
        chunks = split_audio_chunks(mp3_path, chunk_sec, tmp_dir)

        if not chunks:
            # ffmpeg 切割失敗，退回整段模式（加長逾時）
            print("[WARN] 退回整段模式（逾時上限延長至 1800 秒）")
            return _transcribe_single(mp3_path, glossary, max_retries, api_timeout=1800)

        print(f"[CHUNK] 共 {len(chunks)} 段")
        parts = []
        for i, chunk in enumerate(chunks):
            print(f"\n[CHUNK] 轉錄第 {i+1}/{len(chunks)} 段（{chunk.name}）")
            part = _transcribe_single(chunk, {}, max_retries, api_timeout=API_TIMEOUT_CHUNK)
            parts.append(f"--- 第 {i+1} 段 ---\n{part}")

    full = "\n\n".join(parts)

    if glossary:
        full = apply_glossary(full, glossary)
        print(f"[OK] 套用對照表 {len(glossary)} 條")

    print(f"[OK] 分段轉錄合併完成（{len(full):,} 字）")
    return full


# ── 主要對外接口 ────────────────────────────────────────────────────────────

def transcribe_audio(mp3_path: Path, glossary: dict, max_retries: int = 10) -> str:
    """
    音訊 → 逐字稿（對外唯一接口）
    切段觸發條件（任一成立即切段）：
    - 時長 > CHUNK_THRESHOLD_MIN 分鐘
    - 檔案大小 > CHUNK_THRESHOLD_MB MB
    """
    duration = get_audio_duration(mp3_path)
    duration_min = duration / 60
    size_mb = mp3_path.stat().st_size / 1024 / 1024

    if duration > 0:
        print(f"[INFO] 音訊時長：{duration_min:.1f} 分鐘，大小：{size_mb:.1f} MB")
    else:
        print(f"[INFO] 無法偵測音訊時長（ffprobe 不可用），大小：{size_mb:.1f} MB")

    need_chunk = _FFMPEG and (
        duration_min > CHUNK_THRESHOLD_MIN or
        size_mb > CHUNK_THRESHOLD_MB
    )
    reason = []
    if duration_min > CHUNK_THRESHOLD_MIN:
        reason.append(f"時長 {duration_min:.0f}分鐘 > {CHUNK_THRESHOLD_MIN}分鐘")
    if size_mb > CHUNK_THRESHOLD_MB:
        reason.append(f"大小 {size_mb:.0f}MB > {CHUNK_THRESHOLD_MB}MB")

    if need_chunk:
        print(f"[CHUNK] 自動切段（{' 且 '.join(reason)}）")
        return _transcribe_chunked(mp3_path, glossary, max_retries)
    elif not _FFMPEG and (duration_min > CHUNK_THRESHOLD_MIN or size_mb > CHUNK_THRESHOLD_MB):
        print(f"[WARN] ffmpeg 不可用，長/大音訊將直接整段上傳（逾時上限 1800 秒）")
        print(f"[TIP]  若要啟用自動切段，請安裝 ffmpeg 並加入 PATH，或放入 tools/ 目錄")
        return _transcribe_single(mp3_path, glossary, max_retries, api_timeout=1800)
    else:
        return _transcribe_single(mp3_path, glossary, max_retries, api_timeout=API_TIMEOUT_SHORT)


# ── 獨立執行入口 ────────────────────────────────────────────────────────────

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
