# Bulletin viewer UX — mobile, new tabs, Irish preserved, Next button fix

**Date:** 2026-06-13  
**User:** Frankytyrone

## Requests

- Irish/Gaeilge must never be translated to English in bulletins or OCR
- Bulletin HTML should reflect the PDF well
- PDF and OCR must open in new tabs
- Must be mobile-friendly (PDF viewer, OCR, parish links)
- Archive bug: clicking PDF **Next** scrolled down to OCR section instead of advancing pages
- Remove unprofessional wording ("Jump to OCR Text")
- Parish links (e.g. Ardmore) should open in new tab

## Root cause of Next-button bug

Old archive pages (`docs/bulletins/derry-2026-05-22.html` etc.) had `syncOcrToPage()` in JavaScript — every PDF page change scrolled the OCR panel to the matching page heading. User perceived this as "Next goes to OCR tab/section".

## Changes made

### `ocr/generate_bulletin_pages.py`
- New **tab layout**: PDF tab + Searchable Bulletin Text tab (no side-by-side scroll coupling)
- PDF **Next page →** only changes PDF canvas; does not scroll OCR
- Standalone **`{diocese}-{date}-ocr.html`** for reliable "open text in new tab"
- Respectful labels; mobile CSS (48px touch targets, stacked tabs on phone)
- `regenerate_viewer_from_existing()` + `--regenerate-from` CLI
- Fixed CSS syntax bug (`.search-input` missing closing brace)

### `harvester/templates/diocese_page.html`
- Hero buttons: open archive viewer, download PDF, open bulletin text (all new tab)
- Parish links: larger touch targets, `target="_blank"`
- Disclaimer notes Irish/English preserved as printed

### `harvester/page_renderer.py` + `site_builder.py`
- Pass `archive_viewer_url` and `ocr_standalone_url` from latest bulletin file

### `ocr/convert_bulletin.py`
- Stronger `OCR_PROMPT`: never translate Gaeilge; letter-perfect names/times

### Regenerated locally
- `docs/bulletins/derry-2026-05-21.html`, `derry-2026-05-22.html` (+ `-ocr.html`)
- `docs/dioceses/derry/index.html` updated via script

## Standing requests

- [ ] Push to GitHub when Franky says go
- [ ] Run full `site_builder` after next harvest for all dioceses
- [ ] Tier 0 born-digital PDF text extract (OCR accuracy — separate task)
