# Implementation log — 2026-06-13 (full agreed backlog)

## Implemented in this session

### Phase 1 (prior) + Phase 2 stale safety net
- `harvester/bulletin_freshness.py` — stale URL rejection, `retry_queue.json`
- `harvester/recipe_health.py` — DNS 2-strike recipe inactive
- Wired in `main.py`, `stitcher.py`, `report.py`, `fetcher.py`

### Capture Everything (this session)
- `harvester/html_capture.py` — archive listing detection, dated link pick, content-column print
- `harvester/cloud_urls.py` — Google Drive + OneDrive/SharePoint URL normalization
- No bare `html_link` success without PDF capture attempt
- Recipe `html` action → `print_to_pdf` in `replay.py`
- Manual override `html` type → print, not link
- Extension: OneDrive/SharePoint in `isDocumentUrl`; push recipe requires PDF terminal step

## NOT implemented (honest)

| Item | Why |
|------|-----|
| Google Drive offload (`drive_offload.py`) | Not started — needs Google API credentials |
| OCR correction pass | Not started |
| Headful browser / stealth for bot-wary sites | Not started — needs CI design |
| Password-protected Drive/OneDrive | **Cannot** without login credentials |
| 100% parish harvest success | Requires operator re-training per parish |
| Extension truthfulness P0 fixes (audit) | Partially — recipe validation only |
| Auto DOM boundary without training | Heuristic only (dated link + content selectors), not AI |

## Operator next steps after push

1. Re-train `html_link` parishes ending with **Save page as PDF** or **crop**
2. Watch Sunday harvest `retry_queue.json` + `stale_rejected` in report
3. Fix failing parishes from `report.json` (recipe drift)
