from __future__ import annotations

import sys
from pathlib import Path
from pathlib import Path as _P

ROOT_DIR = _P(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import pytesseract
except Exception:
    print("pytesseract not available")
    sys.exit(1)

try:
    from app.ocr_pipeline.pdf_utils import iter_pdf_pages_as_images  # type: ignore
except Exception:
    print("iter_pdf_pages_as_images not available")
    sys.exit(1)

from PIL import ImageFilter, ImageOps

if len(sys.argv) < 2:
    print("Usage: dump_ocr_preview.py <PDF_PATH> [pages]")
    sys.exit(1)

pdf_path = sys.argv[1]
max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3

print("Preview OCR for:", pdf_path)
count = 0
for idx, img in iter_pdf_pages_as_images(str(pdf_path), dpi=300):
    g = img.convert("L")
    g = ImageOps.autocontrast(g)
    g = g.filter(ImageFilter.MedianFilter(size=3))
    g = g.point(lambda x: 255 if x > 180 else 0)
    text = pytesseract.image_to_string(g, lang="fra+eng") or ""
    print("\n=== PAGE", idx, "===\n")
    print(text[:4000])
    count += 1
    if count >= max_pages:
        break
