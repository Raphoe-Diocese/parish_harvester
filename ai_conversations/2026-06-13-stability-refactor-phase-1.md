# Stability refactor — phase 1 implemented

**Date:** 2026-06-13  
**User:** Frankytyrone

## Approach

Prune not fell: new small modules, fault isolation in CI, no deletion of fetcher/extension/recipes.

## Implemented

### New modules
- `ocr/text_extract.py` — Tier 0 born-digital PDF text (free, before vision OCR)
- `ocr/parish_splitter.py` — split mega OCR by parish name for summaries/events
- `harvester/site_health.py` — DNS-only 2-strike NXDOMAIN (never marks slow/HTTP dead)
- `scripts/run_site_health.py` — weekly DNS probe CLI

### Pipeline fixes
- `ocr/convert_bulletin.py` — Tier 0 first; stub HTML on total failure (exit 0, not belly-up)
- `ocr/generate_bulletin_pages.py` — per-parish chunks for summaries, diffs, events
- `harvester/events_extractor.py` — bingo/ceili/social keywords + no-translate rule

### CI isolation
- `.github/workflows/test.yml` — tests on push/PR
- `harvest.yml` — tests advisory (`continue-on-error`), harvest still runs
- `ocr-bulletin.yml` — per-diocese failure isolation
- `.github/workflows/site-health.yml` — weekly DNS snapshot

### Docs
- `docs/ARCHITECTURE.md` — layer diagram and what not to delete

### Tests
- `tests/test_pipeline_modules.py` — 7 tests, all pass

## Not yet (phase 2)
- Google Drive offload
- OCR correction pass
- Auto-mark recipes inactive from site_health
- Slice fetcher.py / content.js
- Push to GitHub (await Franky)
