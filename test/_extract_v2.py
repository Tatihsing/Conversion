"""擷取 v2 PDF 各頁為 PNG，供視覺比對"""
import sys
sys.path.insert(0, r"D:\錄音檔\meeting-auto")

import subprocess, os
from pathlib import Path

pdf_path = Path(r"D:\錄音檔\meeting-auto\test\2026-05-06_製造部門檢討會議_v2.pdf")
out_dir = pdf_path.parent

# 用 Chrome headless 截圖 HTML（PDF 已產好，直接看 HTML）
html_path = pdf_path.with_suffix('.html')

# 改用 Python 內建方式：將 PDF 用 fitz (PyMuPDF) 轉成圖片
# 如果沒有 fitz，就直接提示使用者開啟 PDF 比對
try:
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)
        out_file = out_dir / f"_v2_page{i+1}.png"
        pix.save(str(out_file))
        print(f"[OK] 擷取第 {i+1} 頁 → {out_file.name}")
    doc.close()
except ImportError:
    print("[INFO] 沒有 PyMuPDF，請直接開啟 PDF 檔案比對")
    print(f"  新版：{pdf_path}")
    print(f"  標準：{pdf_path.parent / 'becker.pdf'}")
