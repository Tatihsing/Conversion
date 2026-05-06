"""Extract pages from current output PDF."""
import fitz
from pathlib import Path

test_dir = Path(r"D:\錄音檔\meeting-auto\test")

for pdf_name in test_dir.glob("2026*.pdf"):
    doc = fitz.open(str(pdf_name))
    print(f"FILE: {pdf_name.name}, Pages: {len(doc)}")
    for i in range(len(doc)):
        page = doc[i]
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        img_path = test_dir / f"_current_page{i+1}.png"
        pix.save(str(img_path))
        print(f"[IMG] Saved: {img_path.name}")
    doc.close()
print("Done!")
