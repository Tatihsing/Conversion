"""Extract text and render pages from both PDFs for comparison."""
import fitz
from pathlib import Path

test_dir = Path(r"D:\錄音檔\meeting-auto\test")

for pdf_name in ["becker.pdf", "2026-05-05_製造部門檢討會議.pdf"]:
    pdf_path = test_dir / pdf_name
    if not pdf_path.exists():
        print(f"[SKIP] {pdf_name} not found")
        continue
    
    doc = fitz.open(str(pdf_path))
    print(f"\n{'='*60}")
    print(f"FILE: {pdf_name}")
    print(f"Pages: {len(doc)}")
    print(f"{'='*60}")
    
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        print(f"\n--- Page {i+1} (size: {page.rect.width:.0f} x {page.rect.height:.0f}) ---")
        print(text[:3000])
        if len(text) > 3000:
            print(f"... (truncated, total {len(text)} chars)")
        
        # Render page as image
        mat = fitz.Matrix(2, 2)  # 2x zoom for clarity
        pix = page.get_pixmap(matrix=mat)
        img_path = test_dir / f"_{pdf_name.replace('.pdf', '')}_page{i+1}.png"
        pix.save(str(img_path))
        print(f"[IMG] Saved: {img_path.name}")
    
    doc.close()

print("\nDone!")
