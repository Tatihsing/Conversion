"""
transcribe_srt.py
本地影音轉 SRT 字幕工具：使用 faster-whisper
MP3/MP4/M4A/WAV → SRT 字幕檔
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import timedelta
from .shared import pick_media_file


LANGUAGE  = "zh"
BEAM_SIZE = 5

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
        print("\n[INSTALL] 首次使用字幕功能，安裝 faster-whisper 中...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "faster-whisper"],
            capture_output=False
        )
        if result.returncode != 0:
            print("[ERR] 安裝 faster-whisper 失敗！")
            return False
        print("[OK] faster-whisper 安裝完成\n")
        return True


def detect_device() -> tuple:
    try:
        import ctranslate2
        if hasattr(ctranslate2, "get_cuda_device_count") and ctranslate2.get_cuda_device_count() > 0:
            types = ctranslate2.get_supported_compute_types("cuda")
            if types:
                return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def format_srt_time(seconds: float) -> str:
    total_sec = int(seconds)
    ms = int((seconds - total_sec) * 1000)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_to_srt(audio_path: Path, model_size: str = "medium") -> str:
    from faster_whisper import WhisperModel

    device, compute_type = detect_device()

    print(f"\n[MODEL] 載入 faster-whisper {model_size} 模型...")
    print(f"        裝置：{device.upper()}  精度：{compute_type}")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print(f"[OK] 模型載入完成")

    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"\n[MIC] 開始轉錄：{audio_path.name}（{file_size_mb:.1f} MB）")

    start_time = time.time()
    segments, info = model.transcribe(
        str(audio_path), language=LANGUAGE, beam_size=BEAM_SIZE,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    )

    srt_lines = []
    last_pct = -1
    detected_duration = info.duration or 0
    idx = 0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        idx += 1

        pct = int(seg.start / detected_duration * 100) if detected_duration > 0 else 0
        if pct != last_pct and pct % 5 == 0:
            elapsed = time.time() - start_time
            print(f"  [{pct:3d}%] 已處理至 {format_srt_time(seg.start).split(',')[0]}，耗時 {elapsed:.0f} 秒")
            last_pct = pct

        srt_lines.append(f"{idx}")
        srt_lines.append(f"{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}")
        srt_lines.append(text)
        srt_lines.append("")

    elapsed_total = time.time() - start_time
    print(f"\n[OK] 轉錄完成，耗時 {elapsed_total:.0f} 秒")

    return "\n".join(srt_lines)


def run():
    """SRT 字幕轉錄主流程"""
    print("\n" + "=" * 50)
    print("  🎬 影音轉 SRT 字幕（faster-whisper）")
    print("=" * 50)

    if not _ensure_faster_whisper():
        return

    device, _ = detect_device()
    device_label = "GPU (CUDA) ✅" if device == "cuda" else "CPU"
    print(f"\n[裝置] {device_label}")

    print("\n請選擇轉錄模型：")
    for key, (name, desc) in MODEL_OPTIONS.items():
        print(f"  [{key}] {name:10s} - ({desc})")
        
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

    print("\n[DIR] 請選擇影音檔案...")
    input_file = pick_media_file()
    if not input_file:
        print("[ERR] 未選擇檔案，返回主選單。")
        return

    print(f"[OK] 已選擇：{input_file}")

    srt_content = transcribe_to_srt(input_file, model_size)
    srt_path = input_file.parent / f"{input_file.stem}.srt"
    srt_path.write_text(srt_content, encoding='utf-8')

    print("\n" + "=" * 50)
    print(f"[SAVE] 字幕檔已儲存：")
    print(f"  {srt_path}")
    print("=" * 50)
