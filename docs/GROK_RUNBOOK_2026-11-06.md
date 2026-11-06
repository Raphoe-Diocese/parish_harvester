# Grok 4.6 runbook — 06/11/2026 (forensic audit + autopilot plan)

Written 06/11/2026 from live `parishes/parish_status.json` on `main`, `.github/workflows/*.yml`, recipe folder scan, run logs from today, and `GAMEPLAN.md` / Dropbox Harvester GAMEPLAN. Supersedes the order in `docs/GROK_PLAN_2026-09-12.md` for **bulletin coverage**. Website/OCR cards in that older file still live in `docs/WEBSITE_OCR_BACKLOG.md` — do not start a second list.

Goal (Frank, one sentence): get as many real weekly bulletins as possible, automatically, without the agent stopping to wait.

---

## 0. Numbers (06/11/2026, proved from `parish_status.json`)

| Bucket | Count | Meaning |
|---|---|---|
| ok | 412 | PDF for harvest week |
| failed | 71 | recipe/timeouts/wrong file |
| stale | 52 | recipe worked, parish has not posted this week (honest) |
| skipped | 775 | recipe has `skip:true` — **not being harvested** |
| actionable | 125 | what the Problems tab shows |

Of the 775 skipped: 25 are Facebook-only, 5 have no URL, **~470 have a non-Facebook, non-diocese `start_url` that was never proved** (e.g. dublin 141, meath 51, limerick 50, armagh 47, cashel_and_emly 42, cloyne 40, waterford_and_lismore 40). This is the real untapped pool — **not** the 125 actionable.

Actionable by diocese: Killaloe 20, Down & Connor 18, Cork & Ross 13, Dublin 13, Clogher 9, Achonry 8, Derry 6, Armagh 5, Kerry 5, rest ≤4.

---

## 1. Forensic findings

### 1a. Works (proved)
- Harvest engine: 412 ok. Per-parish concurrency groups let several single-parish runs go at once.
- `scripts/push_harvest_results.py` merges only the target parish / diocese rows into `parish_status.json` (proved: Ashbourne row `last_tested_at` 15:13 after run 15:10).
- Recipe Brain hub scan (`recipe-brain-hunt.yml`, every 6h): 95 "Recipe Brain" commits since 01/10, last run 06/11 12:27 green.
- CI `test.yml` runs on every PR (green on #475, #476, #478 today).
- Recipe types proven this week: `predicted_dated_pdf` with PDF `start_url`, canva image, drive year-folder, `http_scrape_newest_pdf`, HTML print, PNG redirect.

### 1b. Partly works
- **Brain unskips slowly:** `--limit 25` per 6h = 100/day max, and skipped is still 775. Needs a bigger limit, a metric ("unskipped today"), and new strategies (see Card 5).
- **Stale handling:** honest, but one weekly cron (`0 9 * * 0` Sunday UTC). `retry_queue.json` is written but only `bulletin_freshness.py` and `mega_pdf_git.py` reference it — **nothing schedules retries**. Parishes that post Mon–Sat are stale all week.
- **OCR** runs `0 13 * * 0` only. Viewer refresh depends on Sunday.
- Extension 1.61.46: works for training, but Problems tab depends on `actionable_keys`; pasted URL lists never reach recipes automatically.

### 1c. Says it works but doesn't
1. **Green workflow ≠ parish ok.** Run [42240603541](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/42240603541) (Ashbourne) concluded `success`; `parish_status.json` row = `failed` ("wp-json media … no dated"). Armagh run 42236085551 `success`, row `timeout`. Always read the **row**, never the run colour.
2. **Homepage text is static:** "Updated 01/11/2026 / Bulletins ready @ 16:00" while today is 06/11 — it is the last Sunday run, not a live health signal.
3. **Gameplan lines "Not checked on parishpress.ie"** repeat all week. Nothing this week was live-proved on the public site.
4. **Dispatch 422** when the `diocese` input is not an exact list value (`galway`, `ardagh_and_clonmacnoise` fail). Valid values are in `harvest.yml` lines ~12–40 (`galway_diocese`, `ardagh_diocese`, `meath_diocese`, `dublin_diocese`, `armagh_diocese`, …).
5. Recipe says `ok` after a first good week, then silently drifts: pinned folders (`/2026/09/` → `/2026/11/`, Armagh), Drive folder ids, Wix hashes. Only the next harvest reveals it.

### 1d. Broken / hiding
1. **Last-write-wins generated files.** Every single-parish harvest rebases onto main and logs "Resolved harvest output conflicts in favor of this harvest" for **~30 files**: `Bulletins/report.json`, `report.txt`, `dashboard.html`, all 26 `docs/dioceses/*/index.html`, `docs/index.html`, `docs/manifest.json`. Parallel runs overwrite each other's generated pages/report. `parish_status.json` is protected by row-merge; the rest is not. **Single-parish runs should not commit `docs/dioceses/*` or full `report.json`.**
2. **Each single-parish run runs the full pytest suite** (~2 min) before a ~2 min harvest. 91 test files. Fine for CI, slow for a 125-parish loop. (Check `harvest.yml` inputs for an existing skip-tests path before adding one — history shows "tests skipped" re-sends.)
3. **Another PR is racing on the same parishes:** `fix/dublin-timeouts-blessington-ashbourne` (Run tests **failed** 42241841984). Two agents on Blessington/Ashbourne = wasted work. One chat, one job.
4. **UTF-8 BOM** in `parishes/recipes/ardagh/kiltubrid.json` — plain `json.load(..., encoding="utf-8")` fails; 51 places in `harvester/*.py`/`main.py` read recipes with plain utf-8. Fix the file (rewrite without BOM) and load with `utf-8-sig` in the recipe loader.
5. **Giant files:** `harvester/replay.py` 235 KB, `fetcher.py` 106 KB, `extension/content.js` 387 KB. Do not rewrite — slice gradually (AGENTS.md).
6. **Duplicate / competing plans:** 11 markdown plans (older audit). Only these three live: `AGENTS.md`, `docs/WEBSITE_OCR_BACKLOG.md`, `GAMEPLAN.md` (+ Dropbox copy).
7. **Hub scan needs proof gate:** "unskips only after GET 200 + %PDF + date" — confirm it never unskips with a stale date (it should create `stale`, not `ok`).

---

## 2. Rules Grok obeys (paste into every chat)

- Frank: beginner, shuts down on dumps. Answer: Bottom line (1–2 sentences) → What to do (≤5 steps) → one warning only if needed → Gameplan this turn (Written down / Done with evidence / Next / Parked). Dates **DD/MM/YYYY**. Irish stays Irish. Never invent dates/Mass times/OCR.
- **Truth:** never say done/fixed/live without proof **this turn**: a `parish_status.json` row on `main`, a run link **plus** the row, or the live URL. Workflow green ≠ parish ok.
- **No waiting.** After every dispatch, immediately start the next parish. Poll with one `gh run list` batch every few parishes. Never `AwaitShell`/sleep on a run.
- **Max 8 files per fix. No `_tmp_*` in repo. Two failed tries on one parish → park it with a one-line note, move on (do not stop the loop).**
- Mega PDF stays on (`HARVEST_MEGA_PDF=1`). Do not run a full harvest or download mega PDFs on Frank's laptop (16 GB).
- Do not pin dated filenames, Drive file ids, or Wix/WordPress hash names. Prefer scrape / predicted / folder-listing strategies.
- PowerShell: `;` not `&&`. No heredocs (`<<`). Commit with a plain `git commit -m "…"` string. Python: `C:\Users\Digital Admin\AppData\Local\Programs\Python\Python311\python.exe`. Write files with the editor tool (no BOM).
- After any extension change: bump `extension/manifest.json`, tell Frank "Reload at chrome://extensions".
- Memory: after each batch, prepend a dated block to `GAMEPLAN.md` **and** `C:\Users\Digital Admin\Dropbox\Cursor gameplans\Harvester\GAMEPLAN.md`.

---

## 3. Front-load permissions (do this FIRST, once, so nothing stops)

Run these in the first minute so every approval card appears together. Tell Frank: **click Always-allow on each card**.

```powershell
cd "C:\Users\Digital Admin\AppData\Local\Temp\ph_pub"
git fetch origin main
git switch -c grok/permissions-probe origin/main
gh auth status
gh workflow list
gh run list --limit 3
gh workflow run "Recipe Brain hub scan"
gh pr list --limit 3
git switch main
git pull origin main
```

Why: past stalls were `git checkout main` / `git pull` (blocked by Auto-review), `gh pr merge`, and `gh workflow run`. If a card is blocked, retry the **same** command once with approval; do not swap commands.

Better, permanent fix (Frank, one time): **Cursor → Settings → Agents/Features → Auto-run** → set Command allowlist to include `git`, `gh`, `python`, `rg`, or use "Run Everything" for this project. (Exact menu wording may differ — I could not verify it from here.)

Safest workflow that avoids the blocks: **never `git checkout main` for work.** Branch from remote: `git fetch origin main; git switch -c hunt/<name> origin/main`. Merge via `gh pr merge N --merge --delete-branch`, then `git fetch origin main` only (not `pull` on main).

---

## 4. Cards — run top to bottom, never wait between them

Each card: **Goal / Files / Commands / Proof**. Park after two failed tries; continue.

### A1 · Autopilot loop (Grok's standing procedure) — do this continuously
1. Read `parishes/parish_status.json` → `actionable_keys` (A–Z). Take the next **3** keys not in `Bulletins/.grok_parked.txt` (create it; list `key | reason | date`).
2. For each key: open its recipe (`parishes/recipes/*/<key>.json`) → fetch the live site (WebFetch / `python -c urllib` with `User-Agent: Mozilla/5.0`, `ssl._create_unverified_context()` when cert errors) → find this week's file (look for `YYYY/MM` folder drift, new category, Canva/Drive, Irish months, weekend-range names).
3. Fix recipe (strategy from §5). One branch for up to 3 parishes: `git fetch origin main; git switch -c hunt/<a>-<b>-<c> origin/main`.
4. `git add parishes/recipes/...; git commit -m "..."; git push -u origin HEAD; gh pr create --head <branch> --title "..." --body "..."`.
5. **Do not wait for CI.** Start the next 3 parishes. When a PR's `test` check is green (`gh pr checks N`), `gh pr merge N --merge --delete-branch`, then dispatch:
   `gh workflow run "Harvest Parish Bulletins" -f target_parish=<key> -f diocese=<EXACT_diocese_value>`
6. Every ~15 min do one batch check: `gh run list --workflow="Harvest Parish Bulletins" --limit 20` **and** read the `parish_status.json` row for each key on `main` (via `gh api repos/Raphoe-Diocese/parish_harvester/contents/parishes/parish_status.json?ref=main -H "Accept: application/vnd.github.raw"`). Only the row says ok / stale / failed.
7. Honest outcomes: `ok` = done. `stale` = recipe good, site not posted → leave, re-dispatch Mon/Wed (Card 3). `failed` again → park with reason.

Proof per parish: `parish_status.json` row on `main` with `last_tested_at` after your dispatch.

### A2 · Frank's pasted websites (find them, wire them)
- Goal: every URL Frank pasted in chats becomes a recipe/queue entry.
- Sources: (1) `C:\Users\Digital Admin\Dropbox\Cursor gameplans\Harvester\GAMEPLAN.md` — search `pasted`, `Frank pasted`, `hunt odd leftover links`, `cloud dig hits` (e.g. line ~637: ballyhaunisannagh MCN 22, bayside MCN 453, edenderry MCN 434); (2) `C:\Users\Digital Admin\.cursor\projects\c-Users-Digital-Admin-AppData-Local-Temp-ph-pub\agent-transcripts\*.jsonl` — extract only **user message** lines containing `https?://`. Use `rg -o "https?://[^\\s\"')>]+"` on those files; do **not** open whole transcripts or `state.vscdb`.
- Output: new file `parishes/frank_pasted_urls.txt` (`url | source chat/date | matched_recipe_key or NONE`). For each `NONE`: find the parish key (match `display_name`/domain in `parishes/*_contacts.json`), set recipe `start_url`, `skip:false`, add to Card A1 queue. Commit file + recipes in ≤8-file PRs.
- Proof: count of pasted URLs vs count wired; each wired key gets a harvest row.

### A3 · Retry stale/failed during the week (stops the "stale until next Sunday" problem)
- Goal: second and third harvest pass for `stale`+`failed` only.
- Files: `.github/workflows/harvest.yml` (add `- cron: '0 9 * * 1'` and `'0 9 * * 3'` **or** a new `.github/workflows/retry-actionable.yml`), `scripts/` helper reading `actionable_keys`, `tests/` for the helper. Max 4 files.
- Behaviour: dispatch single-parish harvests for actionable keys in batches of 10 (stagger), skip keys with `consecutive_failures >= 10` (39 today) unless the recipe changed in the last 7 days. Never touches `docs/dioceses/*` (see A4).
- Proof: run on Monday shows `retry-actionable` jobs; stale parishes that posted late flip to `ok` in `parish_status.json`.

### A4 · Stop single-parish runs clobbering docs/report (biggest hidden bug)
- Goal: when `target_parish` is set, commit **only** `parishes/parish_status.json`, `parishes/consecutive_failures.json`, `parishes/retry_queue.json`, `parishes/training_backlog.json`, the one parish PDF if any, and merge that parish's row into `Bulletins/report.json` (`patch_report_for_parishes`). Do not `git add docs/dioceses/ docs/index.html docs/manifest.json Bulletins/dashboard.html`.
- Files: `.github/workflows/harvest.yml` (step "Commit bulletins back to repo"), `scripts/push_harvest_results.py`, `tests/test_patch_report.py`. Max 3.
- Proof: next single-parish run log has **no** "Resolved harvest output conflicts … docs/dioceses/…" line and "Pushed on attempt 1".

### A5 · Fix recipe-file hygiene
- Rewrite `parishes/recipes/ardagh/kiltubrid.json` without BOM; load recipes with `utf-8-sig` in the single recipe loader (grep `read_text(encoding="utf-8")` in `harvester/recipe*.py`, `replay.py`, `main.py`). Add test `tests/test_recipes_no_bom.py` (walk `parishes/recipes`, assert no BOM + valid JSON).
- Max 4 files. Proof: test on `main` green.

### A6 · Brain: unskip the ~470 own-site skipped recipes
- Goal: raise `recipe-brain-hunt.yml` to `--limit 60`, add a per-run log line `unskipped=N proved=M stale=K` and write `parishes/recipe_brain_cursor.json` progress so each night covers new keys. Teach new patterns from today (§5) into `harvester/recipe_brain.py`, `extension/site_memory.js`, `parishes/site_patterns.json`, `docs/RECIPE_BRAIN.md`.
- Gate (must stay): unskip only after GET 200 + `%PDF`/JPEG + date for the harvest week — otherwise leave skipped or mark `stale`.
- Proof: next hub-scan run commit message shows `unskipped=N`; `skipped` count in `parish_status.json` falls week on week (775 → target <500 in 7 days).

### A7 · Find NEW parishes (not on any list yet)
- Follow `docs/DIOCESE_HUNT.md` (kitchen-sink + fingerprint/snapshot) for dioceses with the fewest ok-per-parish (live site cards: Armagh 9/61, Cashel & Emly 3/46, Cloyne 4/46, Dublin 43/196, Elphin 3/38, Killala 1/22, Kilmore 4/36, Tuam 16/51, Ardagh 12/36).
- Discovery sources, in order: (1) mcn.live church pages → **Latest Bulletin** (already a recipe type `mcn_live_parish_page`); (2) churchservices.tv / churchmedia.tv listings; (3) mayo.ie parish-newsletter hub (Killala/Tuam/Achonry); (4) diocese directory → parish website field; (5) `ParishPress` uploader pages for parishes with no website.
- Output per found parish: recipe JSON (`skip:false`), contact row, one harvest. Add each new pattern to `parishes/site_patterns.json` + `extension/site_memory.js` + `extension/html_fingerprint.js`.
- Proof: new `ok` rows in `parish_status.json`.

### A8 · Chrome extension: self-feeding
- Goal: the extension should (a) read `parishes/frank_pasted_urls.txt`/Problems and propose recipes using `site_memory`, (b) offer "Send & test" for the next A–Z key, (c) never invent status in `chrome.storage.local`.
- Files (max 6): `extension/sidepanel.js`, `extension/github_recipe_push.js`, `extension/site_memory.js`, `extension/manifest.json` (bump), tests `tests/test_extension_messaging.py`. Do **not** touch `content.js` wholesale.
- Proof: manifest version on `main`; Frank Reload; Problems tab shows queue order matching `actionable_keys`.

### A9 · Truth dashboard (so "green" can't lie)
- Add to `scripts/` a small report: for each of the last N harvest dispatches, workflow conclusion vs `parish_status.json` row; print mismatches. Write result into `GAMEPLAN.md` block each session.
- Proof: printed table with at least the Ashbourne/Armagh mismatches above.

---

## 5. Strategy cheat-sheet (use when fixing)

| Symptom | Fix |
|---|---|
| `Total timeout exceeded` | Make `start_url` the PDF itself (`predicted_dated_pdf`); avoid listing challenge pages; raise `total_timeout_s` only as last resort. |
| WordPress month folder wrong | Newest file may be in previous month's folder — scrape listing/media for the newest, don't force month. Armagh moved `/2026/09/` → `/2026/11/`. |
| `wp-json` 403/404 | Use homepage/listing `http_scrape_newest_pdf` with `User-Agent: Mozilla/5.0`. |
| No PDF, only HTML post | `html_text_bulletin` / `print_to_pdf` with `skip_listing_nav: true`. |
| Image-only bulletin | `image_stack` / Canva `_assets/media` largest image; never pin hash. |
| Drive folder | cloud_folder parent → year → `YY.MM.DD`; never pin file id. |
| Irish dates | Deireadh Fómhair = October, Samhain = November (`harvester/utils.py` knows). |
| Weekend ranges | Take later day (`Newsletter-31st-October-1st-November.pdf` → 01/11). |
| TLS errors | `ignore_https_errors: true` in recipe. |
| Shared bulletin (OneFaith / Cork family) | Harvest once under one key; others alias. |
| Site not posted this week | Leave `stale`; do not invent. Retry Mon/Wed (A3). |
| MCN / mayo.ie / churchmedia | See `docs/DIOCESE_HUNT.md` + `harvester/recipe_brain.py`. |

Valid `diocese` dispatch values: read `harvest.yml` lines 12–40 first (e.g. `meath_diocese`, `dublin_diocese`, `galway_diocese`, `armagh_diocese`, `ardagh_diocese`, `cork_and_ross`, `clogher_diocese`, `derry_diocese`). Wrong value → HTTP 422, not a recipe bug.

---

## 6. Definition of done for the session

Not "I merged PRs". Done = `parish_status.json` on `main` shows a higher `ok` count than 412 (and fewer `failed`), plus a one-line count in `GAMEPLAN.md` and the Dropbox copy. Live-site claims only after opening https://www.parishpress.ie/ and the diocese page.

## 7. Parked (do not start)
OCR reader polish, Problems console polish, parishpress.ie look, no-website ParishPress uploader emails, splitting `replay.py`/`content.js`. See `AGENTS.md` locked order.
