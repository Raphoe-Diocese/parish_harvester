"""Tesseract column OCR on Annagry image bulletin. Do not commit."""
from ocr.sparse_page_ocr import ocr_pdf_page_lines, ocr_lines_look_usable
from ocr.text_extract import page_text_char_count

lines = ocr_pdf_page_lines("docs/parishes/raphoe/annagryparish.pdf", 0)
print("chars", page_text_char_count(lines), "usable", ocr_lines_look_usable(lines))
for ln in lines[:60]:
    print(ln[:140])
print("---TAIL---")
for ln in lines[-20:]:
    print(ln[:140])
