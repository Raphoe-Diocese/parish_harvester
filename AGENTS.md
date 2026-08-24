# Parish Harvester — Agent guide

## Product (what this repo does)

1. **Train** parish bulletin recipes in the Chrome extension (Parish Trainer).
2. **Push** recipes to GitHub (`parishes/recipes/<diocese>/<key>.json`).
3. **Harvest** current-week PDFs via GitHub Actions (`python main.py`).
4. **Fix** failures from the extension Problems tab → retrain → Send & test.

Collated Bulletin (mega PDF) stitching is **core production behaviour, not optional**. Production GitHub Actions harvests must generate the collated mega PDF (`harvest.yml` sets `HARVEST_MEGA_PDF=1`), because OCR and the public diocesan text-bulletin viewer pages depend on it. Do not disable mega PDF generation unless the user explicitly asks. (Single-parish `--target-parish` test runs still skip it — that's separate and intentional, see `main.py`.)

**Mega PDF is core.** The whole product depends on: harvest parish bulletins → collated mega PDF → OCR → searchable diocesan viewer.

**Website / OCR backlog:** before any viewer, OCR, or `docs/` page work, read and update [`docs/WEBSITE_OCR_BACKLOG.md`](docs/WEBSITE_OCR_BACKLOG.md). That file is the living checklist (850px desktop / 450px mobile, parish OCR headers, new-tab links, mega PDF stays on). Do not start a second competing list.

**Everything else** (repo cleanup, workflow fixes, dead code) goes in [`GAMEPLAN.md`](GAMEPLAN.md). Three lists only: this file for product order, the backlog for website/OCR, `GAMEPLAN.md` for the rest.

**Do not lie about done.** Never tell Frank a website/OCR/viewer job is finished unless you have checked the **generated files that GitHub Pages deploys** (`docs/index.html`, `docs/dioceses/`, `docs/parishes/`) AND, after merge+Pages, the **live URL** (e.g. https://www.parishpress.ie/). Tests or Python-only edits are not enough. If it is not on the live page, say “not live yet”. Do not tick backlog items done without the live check.

## PHASE PLAN

### Phase 1: Core capture reliability
- PDF capture
- HTML bulletin capture
- image bulletin capture
- Google Drive / OneDrive / cloud links
- timeout handling
- stale/outdated recipe handling

### Phase 2: OCR reliability
- OCR failure must be visible
- reject obvious junk pages
- preserve Irish/Gaeilge/bilingual text exactly
- do not delete short real notices

### Phase 3: Recipe repair A-Z
- fix failed parishes in A-Z order
- one parish at a time or small batches of 3
- every fix needs a proof pack before commit
- proof pack must include source page, found bulletin URL, HTTP check, PDF check, date check, files changed, tests run

### Phase 4: Recipe Brain / Referee
- classify failures more intelligently
- distinguish stale-but-working from broken recipe
- remember successful patterns
- use confidence scores
- flag human review cases
- **Diocese hunt command (all ~24 remaining dioceses):** follow [`docs/DIOCESE_HUNT.md`](docs/DIOCESE_HUNT.md). Kitchen-sink search + fingerprint/snapshot. When a new trick works, write it into `extension/html_fingerprint.js`, `extension/site_memory.js`, and `parishes/site_patterns.json`.

### Phase 5: Chrome extension
- simplify recipe maker
- use fingerprint tools
- hide confusing extras
- make success/failure obvious

### Phase 6: UI polish
- only after capture, OCR, and recipes are reliable

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
| **Diocese hunt command** | [`docs/DIOCESE_HUNT.md`](docs/DIOCESE_HUNT.md) |

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

## Locked fix order (do not divert)

Until this list is finished, do **not** start other work. Park new ideas for a later list.

1. **OCR reader** — prefer embedded PDF text on born-digital pages; vision only for image/banner pages; one pass per diocese (max ~26) then split. Reader UI live.
2. **Problems console** — full work-queue polish
3. **Recipe success** — one parish at a time
4. **parishpress.ie** — live DNS/Pages when user is ready
5. **Site look** — modern pages after OCR

## Parked (later list — do not start yet)

- **Remove the bulletin archive page and nav entirely** — the wider "delete every trace of `…/parish_harvester/bulletins/`" request (2026-07-30) stays parked. The narrower, safe half — publish **this week only** — is **done and live-proved 24/08/2026** (N1 PR #115 merge `41c13064`, N2 PR #127 merge `7fb20550`): `docs/bulletins/` is 14 files, old weeks 404 on parishpress.ie. See the `done` row in [`docs/WEBSITE_OCR_BACKLOG.md`](docs/WEBSITE_OCR_BACKLOG.md) and items N1/N2 in [`GAMEPLAN.md`](GAMEPLAN.md). `docs/bulletins/index.html` must survive — `harvester/site_builder.py` (`_ocr_standalone_url`) falls back to it.

## Dates (user-facing)

Always show **DD/MM/YYYY** (UK) in the extension, dashboards, emails, and site pages.
Keep machine JSON fields as ISO `YYYY-MM-DD` / timestamps. Use `harvester.utils.format_uk_date`
and extension `formatUkDate()`.

## HTML bulletin gotchas (recipe replay)

- Click with no URL change → force navigate to `href` (`replay._click_locator_match`).
- `html` / `print_to_pdf` after click → set `skip_listing_nav: true` so `html_capture` does not leave the article.
- Hide-chrome must use `child.contains(root)` (not `root.contains(child)`) or parents get hidden → blank ~1KB PDF.
- A4 image bulletins may be ~595×841 — keep image_stack min sides low enough.

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
