"""Render Annagry page and measure column gutters. Do not commit."""
from pathlib import Path

from ocr.sparse_page_ocr import render_pdf_page_image

img = render_pdf_page_image("docs/parishes/raphoe/annagryparish.pdf", 0, dpi=120)
print("image", None if img is None else img.size)
if img is None:
    raise SystemExit
out = Path("_tmp_annagry_page.png")
img.save(out)
print("wrote", out, out.stat().st_size)

# ink per x
gray = img.convert("L")
w, h = gray.size
pix = gray.load()
ink = []
for x in range(w):
    s = 0
    for y in range(int(h * 0.08), h):
        if pix[x, y] < 200:
            s += 1
    ink.append(s)
# find low-ink valleys
mid = w // 2
window = max(8, w // 80)
print("width", w, "height", h, "mid ink", sum(ink[mid - window : mid + window]) / (2 * window))
print("left third ink", sum(ink[w // 6 : w // 3]) / max(1, w // 3 - w // 6))
print("center third ink", sum(ink[w // 3 : 2 * w // 3]) / max(1, w // 3))
print("right third ink", sum(ink[2 * w // 3 : 5 * w // 6]) / max(1, w // 6))
# print lowest-ink x in the middle 50%
band = ink[w // 4 : 3 * w // 4]
min_i = min(band)
print("min mid ink", min_i, "at x", w // 4 + band.index(min_i))
