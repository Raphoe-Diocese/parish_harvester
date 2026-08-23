# GAMEPLAN

The one list for everything that is **not** a website/OCR page job and **not** the
locked harvester product order.

| Where the work lives | Which list |
|---|---|
| Website / OCR / `docs/` pages | [`docs/WEBSITE_OCR_BACKLOG.md`](docs/WEBSITE_OCR_BACKLOG.md) |
| Harvester product order | [`AGENTS.md`](AGENTS.md) locked list |
| Everything else | **this file** |

Rules for this file: write new ideas down the turn they arrive. Do not start
**Parked** work. Do not tick anything **done** without proof Frank can see
(a live URL you opened, a file, or a workflow run ID).

Dates shown to Frank are DD/MM/YYYY. Dates inside JSON stay ISO.

---

## 23/08/2026 — Repo slick / this-week site

**The real goal, in one sentence:** the public site should show **this week only**,
and the repo should get slowly lighter — without breaking harvest, the mega PDF,
OCR, or recipes.

Audit only so far. Nothing was deleted, no cleanup PR was opened, no harvest was
run. Everything below was read on `origin/main` at commit `78063f98`.

### What is actually going on (proof, not opinion)

- **`docs/bulletins/` is the only folder on the site that piles up.** 182 files,
  19 MB. 12 of them are this week (`*-2026-08-23*.html`, four dioceses × three
  pages). The other 168 are old weeks going back to 20/05/2026 — 17 MB.
- **`docs/parishes/` does not pile up.** Its filenames have no date
  (`annagryparish.html`, `annagryparish.pdf`, …), so every harvest overwrites
  them. 458 files / 75 MB, all current week. Leave it alone.
- **The tap that fills the archive is `ocr-bulletin.yml`.** It writes
  `docs/bulletins/{diocese}-{TODAY}.html` (+`-ocr`, +`-pdf`) on every run and
  then commits with `git add docs`. `TODAY` is the day the OCR job ran, not the
  Sunday — which is why there are Wednesday and Thursday dates in there.
- **This week's twelve files are load-bearing.** `docs/index.html` links
  `bulletins/{diocese}-2026-08-23-ocr.html` for all four dioceses, and each
  `docs/dioceses/{diocese}/index.html` links both `-ocr.html` and `-pdf.html`.
  `harvester/site_builder.py` also reads the folder and picks the newest date
  (`_latest_viewer` line 431, `_latest_ocr_standalone` line 462,
  `_latest_pdf_standalone` line 1046). Delete the newest set and the homepage
  "read the text" buttons go 404.
- **No live page links to an old week.** Searching every dated `bulletins/…`
  reference in `docs/index.html`, all four diocese pages, `docs/subscribe/` and
  all 458 `docs/parishes/` pages returns only `2026-08-23`. So the 168 old files
  are reachable only by the archive index and by old bookmarks.
- **Harvest is not slow because of the archive.** Sunday's full harvest
  (run `32630174138`) took 70 minutes, and step 11 "Run Bulletin Harvester" was
  68 of those 70. Rebuilding the search index over the whole archive takes
  0.23 s. Do not sell the archive delete as a speed fix — it is a **site**
  fix (17 MB less deployed, 3.7 MB less downloaded by anyone using `/search/`).

### Two real bugs the audit turned up

1. **The harvest's own test gate has been dead.** `harvest.yml` line 103 runs
   bare `pytest`, which does not put the repo root on `sys.path`. In run
   `32630174138` step 8 finished in **0.36 s** with `collected 1 item / 5 errors`
   and `ModuleNotFoundError: No module named 'harvester'`; `pytest.ini` has
   `--maxfail=5` so collection stopped there. `continue-on-error: true` hid it.
   `test.yml` uses `python -m pytest`, which is why CI is green while the
   harvest gate is not. One-word fix.
2. **184 AI bulletin summaries fail on every OCR run.** Every file under
   `Bulletins/summaries/**` reads `{"bullets": null, "error":
   "summary_generation_failed"}` — 184 of 184. Nothing in the repo, the site, or
   the extension ever reads that folder. The loop in
   `ocr/generate_bulletin_pages.py` also `time.sleep(0.5)` between parishes, so
   this is ~92 s of sleeping plus 184 doomed API calls per OCR run. The code
   already has an off switch (`PARISH_AI_SUMMARIES_DISABLE=1`) that
   `ocr-bulletin.yml` never sets.

### NOW — small PRs Frank can say `go` to, one at a time

**N1. Turn off the tap (stop making new old-week pages).** ~4 files.
Add `prune_old_viewers()` to `ocr/generate_bulletin_pages.py` and call it from
`rebuild_indexes()` (already runs at the end of every viewer write). Rule: for
each diocese keep only the newest date's three files; never touch
`index.html` or subfolders. Prune **per diocese** so a diocese that has not been
regenerated yet does not lose its current page. Add one test. Update both lists.
*Risk if wrong:* a diocese page loses its OCR link. Guard with a test that the
newest trio survives.

**N2. Remove the 168 old-week pages that are already published.** 0 code files.
`git rm` every `docs/bulletins/*-<date>*.html` except the newest date per
diocese, then regenerate the index with
`python ocr/generate_bulletin_pages.py --rebuild-indexes`. Keep
`docs/bulletins/index.html` itself — `harvester/site_builder.py` line 1032 falls
back to it when a diocese has no viewer page. GitHub Pages drops the files on
the next deploy because `deploy-pages.yml` builds `_site` from `cp -a docs/.`.
*Risk if wrong:* old bookmarks 404. That is the intent.
*Do N1 first,* or the next OCR run just starts refilling.

**N3. Make the harvest test gate real.** 1 file, one word.
`.github/workflows/harvest.yml` line 103: `pytest -v --tb=short` →
`python -m pytest -v --tb=short`. Leave `continue-on-error: true` so a red test
still cannot stop a Sunday harvest — this only makes the warning honest.
*Risk if wrong:* none to harvest; worst case the step turns red and logs why.

### NEXT — after the three Now items land

- **Stop the 184 failing summaries.** Add `PARISH_AI_SUMMARIES_DISABLE: "1"` to
  the "Generate OCR viewer pages" env in `ocr-bulletin.yml`. 1 file. Then decide
  whether to delete the 188 write-only files in `Bulletins/summaries/` and the
  188 in `Bulletins/diffs/` (2 MB) — nothing reads either.
- **Delete `write_root_index()`** in `ocr/generate_bulletin_pages.py` (lines
  2569–2644, 76 lines). Nothing calls it — the only caller-shaped function,
  `rebuild_indexes()`, calls `write_bulletins_index()` only. If it ever did run
  it would overwrite the real homepage with the old "Parish Bulletin Dashboard"
  and a "Browse the full OCR bulletin archive" link;
  `tests/test_landing_page.py` line 140 asserts that link is *not* on the
  homepage.
- **Empty calendars.** All 186 files in `Bulletins/events/` have
  `"events": []`, so `docs/calendars/*.ics` are 159–181-byte empty shells last
  committed 30/07/2026. Either fix `harvester/events_extractor.py` or drop the
  calendars. Do not leave a dead subscribe link.
- **`docs/search-index.json` is stale and incomplete.** Last committed
  30/07/2026; 999 documents across 12 dates from May–July; Derry and Down &
  Connor only. Two causes: `harvest.yml` never stages it (line 411 stages
  `docs/manifest.json docs/index.html docs/dioceses/` and nothing else), and
  `harvester/manifest_builder.py` line 17 `VIEWER_FILE_PATTERN` omits `raphoe`.
  Same for `docs/reliability.json` (also built from a `recipes/learned/` folder
  that does not exist in the repo) and `docs/feeds/*.xml` (29/07/2026, no
  Clogher). Decide: fix, or stop publishing them.
- **Orphan pages** — reachable only from `docs/sitemap.html`, which nothing
  links to: `docs/badges/`, `docs/embed-examples.html`, `docs/search/`,
  `docs/calendars/`, `docs/feeds/`, `docs/audit/2026-05-22-deep-audit.md`.
  `docs/subscribe/` is linked by nothing at all. **I don't know whether Frank
  wants `/search/` — keep it** until he says. The one I would delete:
  `docs/bulletins/raphoe/index.html`, a hand-written stub from 27/06/2026 with
  24 hard-coded parish URLs, no generator, no inbound link, superseded by
  `docs/parishes/raphoe/` and `docs/dioceses/raphoe/`.
- **`Bulletins/all_bulletins_<date>.pages.json` accumulates** one per harvest
  week (2026-08-16 and 2026-08-23 today, 22 KB). `.gitignore` covers
  `Bulletins/all_bulletins_*.pdf` but not `.pages.json`. Add the pattern and
  drop the old one.

### KEEP — checked, do not touch

- `mega_pdf/` and `docs/mega_pdf/` (66 MB, four PDFs). Core. `HARVEST_MEGA_PDF=1`
  stays.
- `parishes/parish_status.json`, `parishes/recipes/` (163 files), `harvest.yml`,
  `harvester/fetcher.py`, `harvester/replay.py`, `extension/github_recipe_push.js`.
- The **113 loose `Bulletins/*.pdf`** (67 MB). They look like clutter but the
  extension's "View bulletin" fetches them —
  `extension/sidepanel.js` lines 1773 and 1875 build
  `…/main/Bulletins/{key}.pdf`.
- `docs/parishes/` (75 MB). Undated, overwritten weekly, already this-week only.
- `harvester/pattern_detector.py`. My first scan called it unused; it is
  imported by `harvester/fetcher.py` line 84 as a relative import
  (`from .pattern_detector import …`).
- `harvester/cost_tracker.py` and `harvester/retention.py`. No Python importer,
  but `harvest.yml` line 460 and `retention.yml` line 53 call them inline.
- **The extension.** All 22 JS/HTML files are referenced by something; no dead
  file found. `ph_recording_session` (singular) is a leftover, but
  `background.js` line 347, `recipe_diag_kit.js` line 358 and `content.js`
  line 142 read it deliberately as legacy data. No rewrite, no deletion.
- `harvester/scoreboard.py`, `scheduler.py`. Local dev helpers, off every
  workflow path. Harmless. **I don't know if Frank uses them — keep.**

### PARKED — do not start

- **Rewriting git history to shrink the repo.** `.git` is 734 MB. Deleting files
  from the tree does not shrink GitHub's quota. `git filter-repo` / BFG only
  after an explicit yes from Frank.
- **The 47 remote branches.** `cleanup_branches.yml` only matches `copilot/`
  and there are no `copilot/` branches, so it is a no-op today. Cosmetic.
- **Tidying the root markdown pile** (`CURSOR_LAST_RESULT.md`,
  `CURSOR_NEXT_TASK.md`, `FREE_SOLUTION.md`, `PROJECT_PLAN.md`,
  `CHECKPOINTS.md`, `DECISIONS_LOG.md`, `SITE_MAP.md` — most untouched since
  13/06/2026). Cosmetic. Not now.
- **Scaling to 26 dioceses.** `docs/dioceses/` already has 26 folders; 22 are
  ~1.6 KB placeholders. Stays parked per `AGENTS.md`.

### Not the cause — say so out loud

- The archive is not why harvest takes 70 minutes. The fetch step is.
- Local `_tmp_*` files on the Dynabook are **not** on GitHub. Nothing to delete
  there on the remote; just bin them locally.
