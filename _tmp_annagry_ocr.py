"""Compare Annagry PDF extract methods. Do not commit."""
from pathlib import Path

pdf = Path("docs/parishes/raphoe/annagryparish.pdf")
print("exists", pdf.exists(), "size", pdf.stat().st_size if pdf.exists() else 0)

from ocr.text_extract import extract_all_page_lines, page_text_char_count, page_is_sparse

pages = extract_all_page_lines(pdf)
print("default pages", None if pages is None else len(pages))
if pages:
    for i, lines in enumerate(pages):
        print(f"--- default page {i+1} chars={page_text_char_count(lines)} sparse={page_is_sparse(lines)} ---")
        for ln in lines[:25]:
            print(ln[:120])

try:
    import pymupdf
except ImportError:
    print("no pymupdf")
    raise SystemExit

doc = pymupdf.open(str(pdf))
print("\npymupdf pages", doc.page_count)
for page in doc:
    print("images", len(page.get_images()), "text chars", len(page.get_text("text") or ""))
    blocks = page.get_text("blocks")
    print("blocks", len(blocks))
    # sort=True
    sorted_text = page.get_text("text", sort=True)
    print("--- sort=True first 30 lines ---")
    for ln in [x for x in sorted_text.splitlines() if x.strip()][:30]:
        print(ln[:120])
doc.close()
