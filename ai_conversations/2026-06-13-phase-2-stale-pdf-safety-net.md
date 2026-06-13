# Phase 2 + Stale PDF Safety Net — 2026-06-13

## User request
Phase 2 production items **plus** a safety net: if a downloaded PDF is stale, reject it from the mega PDF **or** instruct the crawler to try a different angle.

## Answer: Yes, both are possible

The repo now has a **two-layer** stale bulletin system:

### Layer 1 — At download time (`fetcher.py`)
After a successful PDF download, `check_bulletin_freshness()` inspects the URL date.

If stale:
1. **Auto-retry** one alternate strategy based on parish type:
   - `rescrape_bulletin_page` — re-scan the bulletin listing page
   - `try_date_patterns` — pattern detector for A–H URL parishes
   - `retrain_recipe` / `mistral_heal` — suggested when recipe/AI paths were used
2. If retry finds a current-week bulletin → use that instead
3. If still stale → mark `is_stale=True`, delete PDF, status `error`

### Layer 2 — Before mega PDF stitch (`bulletin_freshness.py` + `main.py`)
Second-pass gate catches anything that slipped through (e.g. undated URL that was actually old).

Writes `parishes/retry_queue.json` with per-parish instructions:
```json
{
  "retry": [{
    "key": "someparish",
    "strategy": "rescrape_bulletin_page",
    "message": "Stale bulletin (2026-05-01) — try rescrape_bulletin_page"
  }]
}
```

### Mega PDF exclusion (`stitcher.py`)
Skips parishes where `is_stale` or `is_fallback` (historical fallback).

### Report (`report.py`)
New `stale_rejected` section in `Bulletins/report.json` and report TXT.

## Phase 2 also added
- `harvester/recipe_health.py` — auto-inactivate recipes when `site_health.json` shows 2-strike DNS NXDOMAIN (never marks slow/HTTP dead)

## Files changed
- `harvester/bulletin_freshness.py` (new)
- `harvester/recipe_health.py` (new)
- `harvester/fetcher.py` — FetchResult fields + `_recover_stale_bulletin`
- `harvester/stitcher.py` — skip `is_stale`
- `harvester/report.py` — `stale_rejected` tracking
- `main.py` — wire safety net + DNS recipe health
- `tests/test_bulletin_freshness.py` (new, 8 tests)
- `.github/workflows/harvest.yml` — commit `retry_queue.json`
- `docs/ARCHITECTURE.md`

## Operator workflow
1. After harvest, check `parishes/retry_queue.json` or report `stale_rejected`
2. Follow `strategy` hint:
   - `rescrape_bulletin_page` — usually fixes itself next Sunday if parish posted late
   - `try_date_patterns` — pattern may have drifted; extension re-train helps
   - `retrain_recipe` — `python main.py --train "Parish Name"`
   - `manual_review` — undated URLs; use Operator Console override
3. Optional: add parish to `parishes/mega_excludes.json` via extension (manual skip)

## Not pushed to GitHub
Per user rule — local only until Franky says go.

## Tests
`py -m unittest tests.test_bulletin_freshness` — 8/8 pass
