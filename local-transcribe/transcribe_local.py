"""
transcribe_local.py
本地語音轉文字稿工具：MP3 / M4A → TXT
使用 faster-whisper，完全離線，不需 API Key

模型選擇建議（CPU 使用者）：
  small    - 快速，中文準確度普通
  medium   - 推薦！20~40 分鐘/小時，準確度佳
  large-v3 - 最準，60~90 分鐘/小時，適合重要錄音
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
    """啟動時自動檢查並安裝缺少的套件"""
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
        return  # 全部已安裝，直接跳過

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
            print("      請以系統管理員身份執行，或手動執行：")
            print(f"      pip install {pkg}")
            input("\n按 Enter 關閉...")
            sys.exit(1)
        print(f"[OK] {pkg} 安裝完成")

    print("\n[OK] 所有套件安裝完成，程式繼續執行...\n")

_ensure_dependencies()

LANGUAGE  = "zh"   # 固定繁體中文
BEAM_SIZE = 5     # 解碼品質（越高越準但越慢，建議 3~5）

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
            title="選擇錄音檔（MP3 / M4A / WAV）",
            filetypes=[
                ("音訊檔案", "*.mp3 *.m4a *.wav *.aac *.ogg *.flac"),
                ("所有檔案", "*.*"),
            ]
        )
        root.destroy()
        return Path(path) if path else None
    except Exception as e:
        print(f"[WARN] 無法開啟選擇視窗：{e}")
        return None

def detect_device() -> tuple[str, str]:
    """
    自動偵測是否有 NVIDIA GPU 可用。
    回傳 (device, compute_type)
      - NVIDIA GPU: ("cuda", "float16")
      - CPU 限定:   ("cpu",  "int8")
    """
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
    td = timedelta(seconds=int(seconds))
    total_sec = int(td.total_seconds())
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"[{h:02d}:{m:02d}:{s:02d}]"

def transcribe(audio_path: Path, model_size: str = "medium") -> tuple[str, str]:
    """
    回傳 (純逐字稿, 帶時間戳逐字稿)
    """
    from faster_whisper import WhisperModel

    device, compute_type = detect_device()

    print(f"\n[MODEL] 載入 faster-whisper {model_size} 模型...")
    print(f"        裝置：{device.upper()}  精度：{compute_type}")
    print(f"        （首次使用會自動下載，請稍候）")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print(f"[OK] 模型載入完成")

    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"\n[MIC] 開始轉錄：{audio_path.name}（{file_size_mb:.1f} MB）")
    print(f"      使用模型：{model_size}  裝置：{device.upper()}")
    if device == "cuda":
        print(f"      預估時間：GPU 加速，約 2~6 分鐘/小時錄音\n")
    else:
        print(f"      預估時間：CPU 模式，約 20~40 分鐘/小時錄音\n")

    start_time = time.time()

    segments, info = model.transcribe(
        str(audio_path),
        language=LANGUAGE,
        beam_size=BEAM_SIZE,
        vad_filter=True,              # 過濾靜音片段，加快速度
        vad_parameters=dict(
            min_silence_duration_ms=500
        ),
    )

    lines_plain = []       # 純文字（不含時間戳）
    lines_stamped = []     # 帶時間戳

    last_pct = -1
    # 取得音訊總時長（秒）供進度計算用
    detected_duration = info.duration or 0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        # 進度百分比
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

    plain_text   = "\n".join(lines_plain)
    stamped_text = "\n".join(lines_stamped)

    return plain_text, stamped_text

def main():
    print("=" * 50)
    print("  本地語音轉文字稿工具（faster-whisper）")
    print("=" * 50)

    # 偵測裝置，決定時間預估
    device, _ = detect_device()
    if device == "cuda":
        time_est = {"1": "2~6 分", "2": "5~15 分", "3": "1~3 分"}
        device_label = "GPU (CUDA) ✅"
    else:
        time_est = {"1": "20~40 分", "2": "60~90 分", "3": "10~15 分"}
        device_label = "CPU"

    print(f"\n[裝置] {device_label}")

    # 模型選擇
    print("\n請選擇轉錄模型：")
    for key, (name, desc) in MODEL_OPTIONS.items():
        base_desc = desc.split('｜')[1] if '｜' in desc else desc
        print(f"  [{key}] {name:10s} - 約 {time_est[key]}/小時  ({base_desc})")
    choice = input("\n請輸入數字（直接 Enter 使用預設 medium）：").strip()
    model_size = MODEL_OPTIONS.get(choice, MODEL_OPTIONS["1"])[0]
    print(f"[OK] 使用模型：{model_size}")

    print("\n[DIR] 請選擇錄音檔案...")
    input_file = pick_file()
    if not input_file:
        print("[ERR] 未選擇檔案，結束。")
        sys.exit(0)

    if input_file.suffix.lower() not in ('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac'):
        print(f"[ERR] 不支援的檔案格式：{input_file.suffix}")
        sys.exit(1)

    print(f"[OK] 已選擇：{input_file}")
    output_dir = input_file.parent

    # 轉錄
    plain_text, stamped_text = transcribe(input_file, model_size)

    # 儲存純逐字稿
    stem = input_file.stem
    plain_path   = output_dir / f"{stem}_逐字稿.txt"
    stamped_path = output_dir / f"{stem}_逐字稿（含時間戳）.txt"

    plain_path.write_text(plain_text, encoding='utf-8')
    stamped_path.write_text(stamped_text, encoding='utf-8')

    print("\n" + "=" * 50)
    print(f"[SAVE] 已儲存以下兩個檔案：")
    print(f"  1. {plain_path}")
    print(f"  2. {stamped_path}")
    print("=" * 50)
    input("\n按 Enter 關閉...")

if __name__ == "__main__":
    main()
