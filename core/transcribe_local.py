"""
transcribe_local.py
本地離線語音轉文字稿：使用 faster-whisper
不需要 API Key，完全離線運作
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import timedelta
from .shared import pick_audio_file


LANGUAGE  = "zh"   # 固定繁體中文
BEAM_SIZE = 5      # 解碼品質

MODEL_OPTIONS = {
    "1": ("medium",   "推薦｜準確度佳"),
    "2": ("large-v3", "高準確｜適合重要錄音"),
    "3": ("small",    "快速｜準確度普通"),
}


def _ensure_faster_whisper():
    """自動安裝 faster-whisper"""
    try:
        import faster_whisper
        return True
    except ImportError:
        print("\n[INSTALL] 首次使用離線轉錄，安裝 faster-whisper 中...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "faster-whisper"],
            capture_output=False
        )
        if result.returncode != 0:
            print("[ERR] 安裝 faster-whisper 失敗！")
            print("      請手動執行：pip install faster-whisper")
            return False
        print("[OK] faster-whisper 安裝完成\n")
        return True


def detect_device() -> tuple:
    """偵測 GPU/CPU"""
    try:
        import ctranslate2
        if hasattr(ctranslate2, "get_cuda_device_count") and ctranslate2.get_cuda_device_count() > 0:
            types = ctranslate2.get_supported_compute_types("cuda")
            if types:
                return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def format_time(seconds: float) -> str:
    """秒數轉 [HH:MM:SS] 格式"""
    total_sec = int(seconds)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def transcribe(audio_path: Path, model_size: str = "medium") -> tuple:
    """
    回傳 (純逐字稿, 帶時間戳逐字稿)
    """
    from faster_whisper import WhisperModel

    device, compute_type = detect_device()

    print(f"\n[MODEL] 載入 faster-whisper {model_size} 模型...")
    print(f"        裝置：{device.upper()}  精度：{compute_type}")
    print(f"        （首次使用會自動下載模型，請稍候）")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print(f"[OK] 模型載入完成")

    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"\n[MIC] 開始轉錄：{audio_path.name}（{file_size_mb:.1f} MB）")
    if device == "cuda":
        print(f"      預估時間：GPU 加速，約 2~6 分鐘/小時錄音\n")
    else:
        print(f"      預估時間：CPU 模式，約 20~40 分鐘/小時錄音\n")

    start_time = time.time()
    segments, info = model.transcribe(
        str(audio_path), language=LANGUAGE, beam_size=BEAM_SIZE,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    )

    lines_plain = []
    lines_stamped = []
    last_pct = -1
    detected_duration = info.duration or 0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        pct = int(seg.start / detected_duration * 100) if detected_duration > 0 else 0
        if pct != last_pct and pct % 5 == 0:
            elapsed = time.time() - start_time
            print(f"  [{pct:3d}%] 已處理至 {format_time(seg.start)}，耗時 {elapsed:.0f} 秒")
            last_pct = pct
        lines_plain.append(text)
        lines_stamped.append(f"{format_time(seg.start)} {text}")

    elapsed_total = time.time() - start_time
    print(f"\n[OK] 轉錄完成，耗時 {elapsed_total:.0f} 秒（{elapsed_total/60:.1f} 分鐘）")
    print(f"     辨識語言信心：{info.language_probability:.1%}")

    return "\n".join(lines_plain), "\n".join(lines_stamped)


def run():
    """本地離線轉錄主流程"""
    print("\n" + "=" * 50)
    print("  💻 本地離線轉逐字稿（faster-whisper）")
    print("=" * 50)

    if not _ensure_faster_whisper():
        return

    device, _ = detect_device()
    device_label = "GPU (CUDA) ✅" if device == "cuda" else "CPU"
    if device == "cuda":
        time_est = {"1": "2~6 分", "2": "5~15 分", "3": "1~3 分"}
    else:
        time_est = {"1": "20~40 分", "2": "60~90 分", "3": "10~15 分"}

    print(f"\n[裝置] {device_label}")
    print("\n請選擇轉錄模型：")
    for key, (name, desc) in MODEL_OPTIONS.items():
        print(f"  [{key}] {name:10s} - 約 {time_est[key]}/小時  ({desc})")
        
    # 帶有 5 秒倒數的輸入機制 (Windows 專用)
    import msvcrt
    print("\n請輸入數字（5 秒後自動使用預設 medium）：", end="", flush=True)
    start_time = time.time()
    input_str = ""
    timeout = 5
    
    while True:
        if msvcrt.kbhit():
            char = msvcrt.getwch()
            if char in ('\r', '\n'):
                print()
                break
            elif char == '\x08':  # Backspace
                if len(input_str) > 0:
                    input_str = input_str[:-1]
                    print("\b \b", end="", flush=True)
            else:
                input_str += char
                print(char, end="", flush=True)
        
        if time.time() - start_time > timeout:
            print(f"\n[TIME] 逾時未輸入，自動選擇預設...")
            break
        time.sleep(0.05)

    choice = input_str.strip()
    model_size = MODEL_OPTIONS.get(choice, MODEL_OPTIONS["1"])[0]
    print(f"[OK] 使用模型：{model_size}")

    print("\n[DIR] 請選擇錄音檔案...")
    input_file = pick_audio_file()
    if not input_file:
        print("[ERR] 未選擇檔案，返回主選單。")
        return
    if input_file.suffix.lower() not in ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac'):
        print(f"[ERR] 不支援的檔案格式：{input_file.suffix}")
        return

    print(f"[OK] 已選擇：{input_file}")

    plain_text, stamped_text = transcribe(input_file, model_size)

    stem = input_file.stem
    output_dir = input_file.parent
    plain_path   = output_dir / f"{stem}_逐字稿.txt"
    stamped_path = output_dir / f"{stem}_逐字稿（含時間戳）.txt"
    plain_path.write_text(plain_text, encoding='utf-8')
    stamped_path.write_text(stamped_text, encoding='utf-8')

    print("\n" + "=" * 50)
    print(f"[SAVE] 已儲存以下兩個檔案：")
    print(f"  1. {plain_path}")
    print(f"  2. {stamped_path}")
    print("=" * 50)
