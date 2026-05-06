"""Extract the NEW 7-page output PDF pages only."""
import fitz
from pathlib import Path

test_dir = Path(r"D:\錄音檔\meeting-auto\test")
pdf_path = test_dir / "2026-05-05_製造部門專案內部檢討會議.pdf"

doc = fitz.open(str(pdf_path))
print(f"FILE: {pdf_path.name}, Pages: {len(doc)}")
for i in range(len(doc)):
    page = doc[i]
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    img_path = test_dir / f"_new_page{i+1}.png"
    pix.save(str(img_path))
    print(f"[IMG] Saved: {img_path.name}")
doc.close()
print("Done!")
