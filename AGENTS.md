# Parish Harvester — Agent guide

## Product (what this repo does)

1. **Train** parish bulletin recipes in the Chrome extension (Parish Trainer).
2. **Push** recipes to GitHub (`parishes/recipes/<diocese>/<key>.json`).
3. **Harvest** current-week PDFs via GitHub Actions (`python main.py`).
4. **Fix** failures from the extension Problems tab → retrain → Send & test.

Mega PDF stitching is **off by default** (`HARVEST_MEGA_PDF=0`). Do not re-enable without explicit user request.

## Single source of truth for “what’s wrong?”

| File | Role |
|------|------|
| **`parishes/parish_status.json`** | **Primary.** One row per parish outcome; `actionable_keys` drives Problems tab. |
| `Bulletins/report.json` | Raw harvest buckets (downloaded/failed/stale_rejected/…). Feeds parish_status. |
| `parishes/consecutive_failures.json` | Failure streak counter. Merged into parish_status. |
| `parishes/recipes/…` | How to download; `skip`/`dead_url` = inactive. |

Extension **must not** invent parish health in `chrome.storage.local`. Storage is only for UX (fix visited, last dispatch time).

## End-to-end flow

```
Extension Send & test
  → pushRecipe() + dispatchHarvestTest()
  → harvest.yml (target_parish set)
  → main.py --target-parish KEY
  → patch_report_for_parishes() + write_parish_status()
  → git commit report.json + parish_status.json + PDF
  → Extension polls parish_status.json (last_tested_at)
  → Problems tab refreshes from actionable_keys
```

## Key files

| Area | Path |
|------|------|
| CLI / orchestration | `main.py` |
| Download engine | `harvester/fetcher.py`, `harvester/replay.py` |
| Reports | `harvester/report.py` |
| **Unified status** | `harvester/parish_status.py` |
| Workflow | `.github/workflows/harvest.yml` |
| Extension push/poll | `extension/github_recipe_push.js` |
| Problems UI | `extension/sidepanel.js` |
| Training toolbar | `extension/content.js` |

## Outcome categories (parish_status)

- `ok` — PDF downloaded for harvest week (not shown in Problems).
- `stale` — Recipe worked; bulletin too old (still actionable).
- `failed` — Harvest/recipe error.
- `html_only` — No PDF captured.
- `disabled` — `# DISABLED` in evidence file.
- `skipped` — Inactive/dead recipe.

## When changing harvest results

1. Update `_result_to_report_entry` / `patch_report_for_parishes` if buckets change.
2. Update `build_parish_status()` in `parish_status.py` (category/outcome logic).
3. Update extension only if new fields are user-visible.
4. Add/update tests in `tests/test_parish_status.py` and `tests/test_patch_report.py`.

## Do not

- Add new extension-only “status” keys for harvest outcomes.
- Use `continue-on-error: true` on the report commit step.
- Block single-parish runs behind full-harvest concurrency (see `harvest-${{ target_parish }}` group).
- Delete `fetcher.py` / `content.js` wholesale — slice gradually.

## Local commands

```bash
python main.py --target-parish bangorparish --diocese all
python -c "from harvester.parish_status import write_parish_status; write_parish_status()"
python -m pytest tests/test_parish_status.py tests/test_patch_report.py -q
```

Reload extension from `extension/` after manifest version bump.
