"""
transcribe_srt.py
本地語音轉字幕檔工具：MP3 / M4A / MP4 / WAV → SRT 字幕檔
使用 faster-whisper，產生標準 SRT 格式，供影音剪輯或播放器使用。
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import timedelta

# 強制 stdout 使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 自動安裝依賴（第一次使用自動執行）────────────────────────────────────────
def _ensure_dependencies():
    REQUIRED = {
        "faster_whisper": "faster-whisper",
    }
    missing = []
    for module, package in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        return

    print("=" * 50)
    print("  首次使用：自動安裝必要套件")
    print("=" * 50)
    for pkg in missing:
        print(f"\n[INSTALL] 安裝 {pkg} 中...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"\n[ERR] 安裝 {pkg} 失敗！")
            input("\n按 Enter 關閉...")
            sys.exit(1)
        print(f"[OK] {pkg} 安裝完成")

    print("\n[OK] 所有套件安裝完成，程式繼續執行...\n")

_ensure_dependencies()

LANGUAGE  = "zh"   # 固定繁體中文
BEAM_SIZE = 5

MODEL_OPTIONS = {
    "1": ("medium",   "推薦｜1 小時錄音約需 20~40 分鐘，準確度佳"),
    "2": ("large-v3", "高準確｜1 小時錄音約需 60~90 分鐘，適合重要錄音"),
    "3": ("small",    "快速｜1 小時錄音約需 10~15 分鐘，準確度普通"),
}

def pick_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="選擇影音檔（支援 MP3 / MP4 / M4A / WAV 等）",
            filetypes=[
                ("影音檔案", "*.mp3 *.mp4 *.m4a *.wav *.aac *.ogg *.flac *.mkv *.mov"),
                ("所有檔案", "*.*"),
            ]
        )
        root.destroy()
        return Path(path) if path else None
    except Exception as e:
        print(f"[WARN] 無法開啟選擇視窗：{e}")
        return None

def detect_device() -> tuple[str, str]:
    try:
        import ctranslate2
        # 更嚴謹的檢查：不僅檢查庫支援，還要確認有抓到實體 NVIDIA 顯卡
        if hasattr(ctranslate2, "get_cuda_device_count") and ctranslate2.get_cuda_device_count() > 0:
            types = ctranslate2.get_supported_compute_types("cuda")
            if types:
                return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"

def format_srt_time(seconds: float) -> str:
    td = timedelta(seconds=float(seconds))
    total_sec = int(td.total_seconds())
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
        str(audio_path),
        language=LANGUAGE,
        beam_size=BEAM_SIZE,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500
        ),
    )

    srt_lines = []
    last_pct = -1
    detected_duration = info.duration or 0

    for i, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue

        pct = int(seg.start / detected_duration * 100) if detected_duration > 0 else 0
        if pct != last_pct and pct % 5 == 0:
            elapsed = time.time() - start_time
            print(f"  [{pct:3d}%] 已處理至 {format_srt_time(seg.start).split(',')[0]}，耗時 {elapsed:.0f} 秒")
            last_pct = pct

        start_str = format_srt_time(seg.start)
        end_str = format_srt_time(seg.end)
        
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start_str} --> {end_str}")
        srt_lines.append(text)
        srt_lines.append("")

    elapsed_total = time.time() - start_time
    print(f"\n[OK] 轉錄完成，耗時 {elapsed_total:.0f} 秒")

    return "\n".join(srt_lines)

def main():
    print("=" * 50)
    print("  本地影音轉 SRT 字幕工具（faster-whisper）")
    print("=" * 50)

    device, _ = detect_device()
    device_label = "GPU (CUDA) ✅" if device == "cuda" else "CPU"
    print(f"\n[裝置] {device_label}")

    print("\n請選擇轉錄模型：")
    for key, (name, desc) in MODEL_OPTIONS.items():
        base_desc = desc.split('｜')[1] if '｜' in desc else desc
        print(f"  [{key}] {name:10s} - ({base_desc})")
    choice = input("\n請輸入數字（直接 Enter 使用預設 medium）：").strip()
    model_size = MODEL_OPTIONS.get(choice, MODEL_OPTIONS["1"])[0]

    print("\n[DIR] 請選擇影音檔案...")
    input_file = pick_file()
    if not input_file:
        print("[ERR] 未選擇檔案，結束。")
        sys.exit(0)

    print(f"[OK] 已選擇：{input_file}")
    output_dir = input_file.parent

    srt_content = transcribe_to_srt(input_file, model_size)

    stem = input_file.stem
    srt_path = output_dir / f"{stem}.srt"

    srt_path.write_text(srt_content, encoding='utf-8')

    print("\n" + "=" * 50)
    print(f"[SAVE] 字幕檔已儲存：")
    print(f"  {srt_path}")
    print("=" * 50)
    input("\n按 Enter 關閉...")

if __name__ == "__main__":
    main()
