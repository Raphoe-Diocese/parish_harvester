# Parish Harvester — Architecture (stability layers)

**Updated:** 2026-06-13

## Principle: prune, don't fell

Large files (`fetcher.py`, `content.js`) stay until slices are proven. New logic lives in **small modules** first; god-files shrink gradually.

## Pipeline layers (failure isolation)

```
Harvest (per-parish errors isolated)
  → Stitch mega PDF
  → Deploy Pages (mega PDFs removed from git after deploy)
  → Retention (zip old files)
  → OCR per diocese (one failure does not abort others)
       Tier 0: ocr/text_extract.py (free, born-digital PDFs)
       Tier 1: Mistral OCR
       Tier 2: Gemini / OpenAI vision
       Stub HTML if all fail (pipeline continues)
  → generate_bulletin_pages.py
       parish_splitter → per-parish summaries, diffs, events
```

## New modules (2026-06-13)

| Module | Role |
|--------|------|
| `ocr/text_extract.py` | Tier 0 PDF text — skip vision OCR when possible |
| `ocr/parish_splitter.py` | Split mega OCR into parish chunks |
| `harvester/site_health.py` | DNS-only dead site detection (2-strike NXDOMAIN) |
| `harvester/bulletin_freshness.py` | Stale PDF rejection + retry queue for mega PDF |
| `harvester/recipe_health.py` | Auto-inactivate recipes from DNS health |
| `harvester/html_capture.py` | Archive-aware HTML → PDF (dated link + content column) |
| `harvester/cloud_urls.py` | Google Drive + OneDrive URL normalization |
| `harvester/browser_launch.py` | Anti-bot browser settings + headful CI fallback |
| `scripts/run_site_health.py` | CLI to probe evidence URLs |

## What we deliberately did NOT delete

- `harvester/fetcher.py` — harvest orchestration (future slice into download/scrape)
- `extension/content.js` — trainer (future slice into pdf_picker, parish_messenger)
- All `parishes/recipes/`, evidence files, `ai_conversations/`
- Full OCR fallback chain (Mistral → Gemini → OpenAI)

## CI behaviour

| Workflow | Isolation |
|----------|-----------|
| `test.yml` | Tests on push/PR — blocks merge quality |
| `harvest.yml` | Tests advisory (`continue-on-error`) — harvest still runs Sunday |
| `ocr-bulletin.yml` | Per-diocese try/catch — Derry failure does not skip Down & Connor |

## Next slices (not yet done)

1. `harvester/drive_offload.py` — Google Drive cold archive
2. `ocr/correction_pass.py` — text-only fix for mass times / names
3. Extract `fetcher.py` download helpers → `harvester/download.py`
4. Auto-apply `inactive` recipes from `site_health.json` (with manual override)
