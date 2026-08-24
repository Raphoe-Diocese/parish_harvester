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

## 23/08/2026 — Brittleness audit (what can lie to us)

**The real goal, in one sentence:** find the places where harvest says `ok` but a
reader gets the wrong week, an error page, or nothing — and the places where one
small failure hides a big one.

Audit only. Nothing was implemented, no recipe was touched, no harvest was run,
no PDF was downloaded. Everything below was read on a fresh clone of
`origin/main` at commit `48280c42`, and the live checks were run 23/08/2026.
This does **not** redo the archive/this-week audit in the section below it.

### The one thing to fix first

**`ok` does not mean the reader gets this week's bulletin.** Three live pages
prove it, all titled `23/08/2026`, all `outcome: ok` in
`parishes/parish_status.json`:

| Live page (checked 23/08/2026) | What it actually shows |
|---|---|
| [`/parishes/clogher/killanny-ocr.html`](https://www.parishpress.ie/parishes/clogher/killanny-ocr.html) | May **2021** — `Ascension of The Lord`, `Pentecost Sunday`, `16th May`. HTTP 200, `Last-Modified: Sun, 23 Aug 2026 22:47:57 GMT` |
| [`/parishes/raphoe/drive-1jmslbrliw-ocr.html`](https://www.parishpress.ie/parishes/raphoe/drive-1jmslbrliw-ocr.html) | Raphoe parish, body header `Sunday 19 July 2026 RAPHOE PARISH NEWSLETTER`. HTTP 200, `Last-Modified: Sun, 23 Aug 2026 23:16:54 GMT` |
| [`/parishes/down_and_connor/sacredheartparishbelfast-ocr.html`](https://www.parishpress.ie/parishes/down_and_connor/sacredheartparishbelfast-ocr.html) | An Apache **503 Service Unavailable** page — `The server is temporarily unable to service your request due to maintenance downtime` |

Readers are being shown Mass times for the wrong week. That is the worst
failure this product can have.

**Why, in code (two gaps, not one):**

1. `harvester/bulletin_freshness.py` `check_bulletin_freshness` returns
   `unknown` when the URL carries no date (line 324, `no_date_in_url`), and
   `harvester/fetcher.py` `_recover_stale_bulletin` line 1972 only rejects
   `verdict.status == "stale"`. So `unknown` is accepted as this week.
   Measured on `origin/main` for target 2026-08-23: of the **112** `ok` rows,
   **64** were genuinely date-checked (`in_bulletin_week`), **39 (35%) came back
   `unknown:no_date_in_url`** — nothing checked the week at all — 8 passed only
   on the grace window, 1 on `upload_folder_matches_target_month`.
2. **No body-date check runs on the normal path.**
   `harvester/fetcher.py` `extract_pdf_bulletin_date` (line 447) is only called
   from `classify_page_capped_pdf` (line 492), which only runs when a PDF
   *exceeds* the page cap. That is why Holy Cross Belfast (13 pages) was caught
   as `stale` and Raphoe parish (short PDF, July body) was not.

`harvester/html_capture.py` `pick_best_link` line 194 makes it worse for HTML
parishes: it accepts a link when `best_score[2]` is set, and `best_score[2]`
(`not_stale`, line 172) is **1 for an undated link**. So on a listing page with
no this-week link, an undated link is followed and printed as this week's
bulletin.

**H1 — small harden.** In `_recover_stale_bulletin`, when the URL verdict is
`unknown` *and* a PDF was produced, read the body date with the existing
`extract_pdf_bulletin_date` and judge it with the existing
`verdict_for_extracted_date`. Both helpers already exist and are already
tested; nothing new is invented. `extract_bulletin_date_from_text`
(`bulletin_freshness.py` line 261) only reads dates off `bulletin` /
`newsletter` / `parish news` heading lines, so it will not trip over a
`© 2012-2026` footer and it does not touch Irish text. ~1 file, ~15 lines,
1 test. Parishes whose PDF has no heading date stay `unknown` → unchanged; only
**provably** old bodies flip to `stale`.
**H1 status 24/08/2026: tests proved, not live.** PR
[#129](https://github.com/Raphoe-Diocese/parish_harvester/pull/129)
(`e39b961e`). Targeted
`python -m pytest tests/test_bulletin_freshness.py tests/test_fetcher_capture_reliability.py -q`
= 44 passed. Undated URL + July heading → `stale`; no heading / this-week
heading stay `unknown`. This does **not** change parishpress.ie until the
next harvest — do not tick H1 done as live/harvested. H2 tests proved. H3 doing.

### Also NOW — two more one-file hardens

**H2. The junk-page guard has no 5xx phrases.**
`harvester/report.py` `_ERROR_PAGE_PATTERN` lines 26–30 matches captcha /
403 / 404 / access-denied wording only. `docs/parishes/down_and_connor/sacredheartparishbelfast.pdf`
(19,231 bytes) is a captured Apache 503 page, it passed the guard, it is
`ok`, and it is live (above). Add `503` / `502` / `500` /
`service unavailable` / `bad gateway` / `gateway time-out` /
`internal server error` / `under maintenance` / `temporarily unavailable` to
that same deliberately-narrow regex. 1 file, 1 regex, 1 test. The existing rule
still holds: it must never fire on "no extractable text", because `image_stack`
photo bulletins legitimately have no text layer.
**H2 status 24/08/2026: tests proved, not live.** PR
[#130](https://github.com/Raphoe-Diocese/parish_harvester/pull/130)
(`389ac77f`). Targeted
`python -m pytest tests/test_report_error_pages.py -q` = 10 passed. Apache
`503 Service Unavailable` / `temporarily unable to service your request`,
`502 Bad Gateway`, and `500 Internal Server Error` flagged; `Collection €500`
and the existing real-bulletin / blank image_stack / unreadable-file cases
not flagged. Same deliberately-narrow regex — no bare `500`. This does
**not** change parishpress.ie until the next harvest — do not tick H2 done
as live/harvested. H3 doing. `harvester/stitcher.py` still has the old
copy of the regex — parked, not edited.

**H3. The 8-day grace window accepts last Sunday as this Sunday.**
`harvester/bulletin_freshness.py` line 289 —
`abs(days_from_target) <= MAX_STALE_DAYS_FROM_TARGET` with the constant at 8
(line 30). `week_window` (line 71) is already the correct Sunday−6…Sunday, so
the whole negative half of the grace window is the bug. This week **8** `ok`
parishes sit at exactly **−7 days** — last Sunday's file:
`limavadyparish` (`16-8-26.pdf`), `st-colmcilles`
(`Parish-Bulletin-16082026.pdf`), `stcolmcillesholywood`, `stgerardsparish`
(`sunday-bulletin-16th-august-2026`), `stteresasparish`
(`…for-sunday-16th-august…`), `stmarysportglenone` and `loughshoreparishes`
(`20th-Sunday-in-Ordinary-Time`, which was 16/08/2026), `parishofmaghera`.
Live proof: [`/parishes/down_and_connor/st-colmcilles-ocr.html`](https://www.parishpress.ie/parishes/down_and_connor/st-colmcilles-ocr.html)
is titled `St Colmcilles Text Bulletin — 23/08/2026` and contains `16 August`.
Harden: make the window one-sided — keep the *ahead* tolerance (parishes really
do post Thursday/Friday for next Sunday; see `_HTTP_SCRAPE_AHEAD_DAYS = 7` in
`harvester/replay.py` line 1573) and drop the *behind* tolerance back to the
bulletin week. ~3 lines.
*The file already admits this:* the comments at lines 45–53 and 124–132 say
antrimparish and st-colmcilles "only passed by accident, via the 8-day grace
window", not on a correct `in_bulletin_week` match.
**Say this out loud before doing it:** 8 parishes flip `ok` → `stale`, the
Problems tab jumps from 15 to about 23, and the homepage ready counts drop.
That is the truth, not a regression — but it must not be a surprise.
**H3 status 24/08/2026: doing.** One-sided ahead grace only (`0 < days <= 8`).
Last Sunday is outside `week_window` and must become stale. Ahead posts
(Thursday/Friday for next Sunday) stay fresh. Do not tick H3 done as live —
`parish_status.json` and parishpress.ie do not change until the next harvest.
H4 not started.

### NEXT — after the three above land

- **H4. `last_tested_at` lies for 158 of 161 parishes.**
  `harvester/parish_status.py` line 223 falls back to
  `report.get("last_patched_at")` for any row with no per-row stamp, and
  `harvester/report.py` line 446 sets `last_patched_at` on *every*
  single-parish patch. Proof on `origin/main`: only **4** report rows carry
  their own `last_tested_at` (`kincasslagh`, `clones`,
  `parishofballinascreen`, `castleblayney`) yet **158** parish_status rows all
  read `2026-08-23T22:36:52+00:00` — Castleblayney's test time. The extension
  shows that date in Problems/Directory, and
  `extension/github_recipe_push.js` lines 591–596 uses "did `last_tested_at`
  change?" to decide a Send & test finished, so two overlapping tests can make
  one parish report the other's result. Harden: drop the fallback (leave
  `null`) or add a separate `status_generated_at`. 1–2 files + tests.
- **H5. Pattern F invents URLs that never existed.**
  `harvester/utils.py` `rewrite_date_url` lines 1064–1073: when no date pattern
  matched the *filename*, it still rewrites any `/YYYY/MM/` within ±1 year of
  target. That is how Bundoran got recorded as
  `http://magheneparish.ie/wp-content/uploads/2026/08/Parish_Newsletter_09.02.2025.pdf`
  — an August-2026 folder with a February-2025 filename, HTTP 404 (already
  proved in `docs/WEBSITE_OCR_BACKLOG.md`). Related: `_D_M_YYYY_DOT_RE`
  (`Newsletter-23.08.2026.pdf`, `utils.py` line 41) can be *read* by
  `extract_date_from_string` but has **no rewrite branch**, so Kilmore-shaped
  filenames fall through to the same blanket folder rewrite. Harden: skip the
  Pattern-F folder-only rewrite when `extract_date_from_string(basename)` finds
  a date — a dated filename we cannot rewrite should stay untouched, not be
  half-rewritten into a 404. The Iskaheen `1.jpg` case the branch was written
  for is unaffected (undated filename).
- **H6. `# DISABLED` disables nothing in the fetcher.** `harvester/fetcher.py`
  contains **zero** references to `DISABLED`; only
  `harvester/parish_status.py` `_parse_disabled_keys` (line 47) reads it, and
  that only changes the *display*. Coleraine (St John), Greencastle and Long
  Tower all keep a live URL line under their `# DISABLED` comment
  (`parishes/derry_diocese_bulletin_urls.txt` lines 264–268, 287–294,
  304–312) and are fetched every single week. Live 23/08/2026:
  `https://greencastleparish.com/` 302s to
  `http://ww80.greencastleparish.com/?subid1=bf7ad5ab-…` → HTTP **502** (the
  parked/affiliate redirect the evidence file flagged on 2026-08-10), and the
  generated page `docs/dioceses/derry/index.html` publishes
  `<a class="parish-link" href="https://greencastleparish.com/" target="_blank" …>Greencastle</a>`.
  Two small hardens: (a) make `parse_evidence_file` skip a `# DISABLED` block;
  (b) in `ocr/generate_bulletin_pages.py` `render_parish_link_grid` line 805,
  do not fall back to an external href for a key whose parish_status outcome is
  `disabled`. Overlaps the 23/08 "useful reader link only if already proved"
  backlog row — that one covered `harvester/diocese_intro.py`; this is the
  A–Z grid, a different generator.
- **No same-origin check after a redirect.** `harvester/fetcher.py`
  `_try_force_html_to_pdf` line 857 returns `url=page.url or url`, and the only
  acceptance test is "PDF ≥ 4096 bytes" (`HTML_RENDER_MIN_BYTES`, line 105).
  An expired parish domain that gets parked can therefore be captured and
  reported `ok` under the squatter's URL. Small harden: reject when the final
  registrable domain differs from the one we asked for.
- **H7. `ok` also does not mean the slice made it into the mega PDF.** 12 of
  113 published parish PDFs are ~1.7 KB placeholders reading *"PDF slice
  unavailable — This parish is marked OK, but its page range could not be found
  in this week's mega OCR"* (`annagryparish`, `stteresasparish`,
  `parishofmaghera`, `clontibret`, `tyholland`, `iskaheenparish`,
  `stgerardsparish`, `saintanthony`, `fintona`, `kilmoreandkillyleagh`,
  `ourladyqueenofpeacekilwee`, `newtownbutler`). The placeholder text is
  honest; the `ok` and the homepage ready count are not. Harden: surface a
  `slice_missing` flag rather than redefining `ok` — do **not** touch the mega
  PDF for this.
- **H8. Two URL encoders, only one of them hardened.** The Clones fix,
  `harvester/utils.py` `quote_http_url` (line 375), is used at just **3** call
  sites, all in `harvester/replay.py` (981, 1707, 1855). `harvester/fetcher.py`
  still hand-rolls `.replace(" ", "%20")` at 833, 1177, 1310, 1818, 2032, 2270
  and 2327, plus `harvester/pattern_detector.py` line 135. `.replace()` misses
  non-ASCII (Irish fadas in a filename), `[`/`]` and quotes; **neither** helper
  handles a raw space in the *query string* or a literal `#` (urlparse turns it
  into a fragment and the server never sees it). Harden: route every site
  through `quote_http_url` and extend it to the query, so the next
  Clones-class URL does not need a per-parish fix.

### CI — one new item, and a note on N3

- **H9. `--maxfail=5` in `pytest.ini` (line 16) hides the suite.** Reproduced
  in this audit: with one dependency missing, `python -m pytest --collect-only`
  reported `99 tests collected, 5 errors` and stopped. With the dependency
  installed the real suite is **562 passed, 1 skipped, 1 xfailed** in 84s. That
  is the same mechanism as the harvest gate's `collected 1 item / 5 errors`, so
  **even after N3 lands**, one bad import will still truncate CI into looking
  nearly green. Harden: drop `--maxfail=5` from `pytest.ini` and keep it as a
  local flag. 1 file, 1 line.
- **Note on N3 (do not duplicate it):** the existing N3 fix stands. Worth
  knowing that adding `pythonpath = .` to `pytest.ini` fixes bare `pytest`
  as well, so it also works for anyone typing `pytest` locally. Same one-line
  spirit — N3's owner can take it or leave it.
- **H10. A silent skip is hiding an open bug.**
  `tests/test_sparse_page_ocr.py` line 161 skips unless
  `docs/parishes/raphoe/annagryparish.pdf` is at least 20,000 bytes. That file
  *is* committed — as a **1,713-byte** "PDF slice unavailable" placeholder — so
  the one test that would catch the open "Annagry image OCR smashed" backlog
  item never runs, in CI or locally. Harden: point it at a small committed
  fixture, or mark it `xfail` so it is visible instead of invisible.

### OCR / generator

- **H11. Diocese viewer HTML is written non-atomically.**
  `ocr/parish_pages.py` line 61 has a hardened `_write_text` (strips NULs,
  atomic replace, 3 retries). `ocr/generate_bulletin_pages.py` writes the
  diocese viewer trio with plain `path.write_text` at lines 2421, 2426, 2431,
  2458, 2463, 2468 and 2534 — the exact files GitHub Pages serves for a whole
  diocese. Already named on the 2026-08-23 "Faithful searchable OCR" backlog
  row ("Windows NUL/lock writes skipped dioceses") and still not fixed here.
  Harden: reuse the same helper. I did **not** reproduce a crash; the concrete
  defect is that the hardened writer exists two files over and is not used.
- Everything else on the OCR list (`_ORDINAL_DUP_RE` eating `22nd`, banner
  swallow, `_is_url_only_line`, Annagry columns) is already owned by the
  2026-08-23 backlog row. Not re-listed here.

### Checked and genuinely fine — do not "fix" these

- `harvest.yml` line 126 keeps `HARVEST_MEGA_PDF: "1"`. Locked, correct.
- The report commit step (`harvest.yml` line 399) has **no**
  `continue-on-error`. Correct.
- `main.py` lines 372–381 make a parish_status write failure loud **and**
  fatal (`::error::` then `raise`). Exactly right.
- Dispatch 403 is already handled with a real message —
  `extension/github_recipe_push.js` line 281, *"PAT missing 'workflow' scope"*.
- The extension does not invent parish health: Problems reads
  `actionable_keys` straight from parish_status
  (`extension/sidepanel.js` lines 1388 and 2521).
- The hide-chrome `child.contains(root)` guard from the AGENTS.md gotcha list
  is correct in **both** copies — `harvester/html_capture.py` lines 120 and 263.
  No blank-1KB regression there.
- `_is_real_pdf` (`harvester/fetcher.py` line 404) now folds in the page-count
  check for every caller. Good.

### I don't know — keep, do not act on these yet

- **Two evidence-file parsers that can drift.** `harvester/fetcher.py`
  `_HEADER_DASH_CLASS` (line 107) accepts `-`, `–` and `—`;
  `harvester/parish_status.py` `_HEADER_RE` (line 30) accepts ASCII `-` only.
  `_parse_disabled_keys` also misses a bullet-prefixed URL that
  `parse_evidence_file` normalises (`fetcher.py` line 304). **Latent, not
  live** — I checked all four evidence files and none uses an en/em dash header
  or a bullet URL today. I don't know whether the extension can ever write one.
  Keep.
- **Ambiguous 2-digit-year dates are resolved by "latest year wins."**
  `harvester/utils.py` lines 265–279 and 291–304 pick `max()` of the two
  readings, and the DDMMYY branch (line 240) and `_YY_MM_DD_RE` branch skip
  `_is_plausible_bulletin_year` while five sibling branches apply it. So
  `27-08-26` reads as 2027-08-26, not 2026-08-27. `_is_plausible_bulletin_year`
  (line 187) also calls `date.today()`, so the same filename can parse
  differently depending on when harvest runs. The real fix is to resolve
  ambiguity against the harvest Sunday instead of by max-year, but
  `extract_date_from_string` takes no target. I found **no live parish** hitting
  this. Keep, and do not touch the locked `tests/test_cloud_folders.py` cases.
- `harvester/replay.py` `_insecure_ssl_context` (line 1539) retries with
  `CERT_NONE` for **any** host with a bad chain, not just mucknoparish.ie —
  while `host_profiles.json` already has an `ignore_https_errors` knob
  (`fetcher.py` line 613, `replay.py` line 3833) that this urllib path ignores.
  Cheap harden if Frank wants it; not urgent.
- `harvester/html_capture.py` line 340: `mode = "archive_nav_print" if navigated
  else "content_print"` where `navigated = page.url`, which is always truthy —
  so the logged capture mode is always `archive_nav_print`. Cosmetic log lie.
- `main.py` line 296 uses only the **first** diocese's contacts file for the
  combined mega PDF, so other dioceses fall back to key-derived display names.
  Cosmetic.

### Not the cause — say so out loud

- This is not an OCR-quality problem. Killanny, Raphoe parish and Sacred Heart
  were OCR'd **accurately**. The pipeline faithfully published the wrong
  document. Improving OCR will not fix any of the three.
- It is not a recipe-training problem either. All three recipes "work" — they
  fetch exactly what they were told to fetch.

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
**Status 24/08/2026: done — PR [#115](https://github.com/Raphoe-Diocese/parish_harvester/pull/115) merged as `41c13064`, confirmed an ancestor of `origin/main` `1c7f7c60`.**
Add `prune_old_viewers()` to `ocr/generate_bulletin_pages.py` and call it from
`rebuild_indexes()` (already runs at the end of every viewer write). Rule: for
each diocese keep only the newest date's three files; never touch
`index.html` or subfolders. Prune **per diocese** so a diocese that has not been
regenerated yet does not lose its current page. Add one test. Update both lists.
*Risk if wrong:* a diocese page loses its OCR link. Guard with a test that the
newest trio survives.
*Built in PR #115:* `prune_old_viewers()` + `rebuild_indexes()` call it first;
`--regenerate-from` protects the date it just rewrote; `BULLETIN_PRUNE_DISABLE=1`
switches it off; 7 tests in `tests/test_bulletin_archive_prune.py`, including
`test_current_week_ocr_and_pdf_links_survive_prune` (site_builder still resolves
every diocese's `-ocr` / `-pdf` page after a prune). Dry run on a **copy** of the
real folder: 168 old pages removed, this week's 12 + `index.html` + the
`raphoe/` subfolder kept. Nothing in `docs/` was regenerated or deleted by that PR.
**Tick this done only after the PR is merged.**

**N2. Remove the 168 old-week pages that are already published.** 0 code files.
`git rm` every `docs/bulletins/*-<date>*.html` except the newest date per
diocese, then regenerate the index with
`python ocr/generate_bulletin_pages.py --rebuild-indexes`. Keep
`docs/bulletins/index.html` itself — `harvester/site_builder.py` line 1032 falls
back to it when a diocese has no viewer page. GitHub Pages drops the files on
the next deploy because `deploy-pages.yml` builds `_site` from `cp -a docs/.`.
*Risk if wrong:* old bookmarks 404. That is the intent.
*Do N1 first,* or the next OCR run just starts refilling.
**Status 24/08/2026: done — PR [#127](https://github.com/Raphoe-Diocese/parish_harvester/pull/127) merged as `7fb20550`, Pages [32678700149](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32678700149) success, live-proved.**
No hand-written `git rm` list: N1's own `prune_old_viewers()` did the delete via
`--rebuild-indexes`, so keep rule and delete rule are one piece of code. Counted
on `1c7f7c60` first instead of trusting the audit — 180 dated files in 60
diocese-date trios, newest `2026-08-23` for all four dioceses, so **168** old
files, exactly as audited. Left behind: 12 this-week pages, `index.html` rebuilt
from 60 links to 4, and `docs/bulletins/raphoe/index.html`. Also had to rebuild
`docs/search-index.json` — it was generated 29/07/2026 and all 999 of its
documents linked pages this PR deletes, which would have turned `/search/` into a
404 machine; it now holds 3 live `2026-08-23` documents. 0 broken dated
`bulletins/…` references anywhere under `docs/`; 50 tests green.
*Live-proved 24/08/2026.* Baseline first: all four old URLs were HTTP 200 live
before the merge. After merge + Pages they are HTTP **404** —
`bulletins/derry-2026-07-19.html`, `bulletins/down_and_connor-2026-05-20.html`,
`bulletins/raphoe-2026-08-21-ocr.html`, `bulletins/derry-2026-05-22-pdf.html`.
This week is untouched: HTTP 200 on all 12 pages, the homepage, `bulletins/` and
all four diocese pages; `bulletins/raphoe-2026-08-23-ocr.html` is 181,306 bytes,
titled `Raphoe Diocese Text Bulletin — 23/08/2026`, 24 parish headers, Irish
still Irish. Live `bulletins/` lists exactly 4 links. Live `/search/` is 200 with
3 documents and **0** dead links. `docs/bulletins/` on `main` is now 14 files.
Full evidence in `docs/WEBSITE_OCR_BACKLOG.md`.

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
