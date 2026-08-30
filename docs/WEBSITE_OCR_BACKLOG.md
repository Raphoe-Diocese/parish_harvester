# Website / OCR living backlog

**Read this file before any website, OCR, diocese viewer, parish page, or mega-PDF viewer work.**

This is the single list. Do not create a second competing plan. Do not mark an item **done** unless you have verified it on **generated** HTML/CSS (the files under `docs/dioceses/`, `docs/parishes/`, `docs/bulletins/`, or a fresh `render_bulletin_viewer_shell` output) — changing Python alone is not enough. Harvest regenerate overwrites live HTML from the canonical generator.

Date format for new rows: `YYYY-MM-DD`. User-facing dates on the site stay **DD/MM/YYYY**.

## Locked product rules (do not “helpfully” undo)

| Rule | Where it lives |
|------|----------------|
| Mega PDF generation stays **on** (`HARVEST_MEGA_PDF=1`) | `.github/workflows/harvest.yml`, `AGENTS.md`, `DECISIONS_LOG.md` |
| Desktop PDF box: locked **850px** + inner scroll (not all parishes down the page) | `ocr/generate_bulletin_pages.py` → `render_bulletin_viewer_shell`, `docs/assets/pdf-inpage-viewer.js` |
| Mobile/tablet (max-width 1024px): `min-height: ~450px` | same function, `@media (max-width: 1024px)` |
| Parish / diocese outbound links open in a **new tab** (`target="_blank"` `rel="noopener noreferrer"`) | viewer shell, parish grids, `docs/assets/pdf-inpage-viewer.js` |
| OCR shows a **parish name header**, real **section headings**, professional spacing | `ocr/bulletin_layout.py`, `ocr_reading_css()` |
| Do not invent events or translate Irish/Gaeilge | `ocr/bulletin_layout.py`, `ocr/convert_bulletin.py` prompt |
| Keep real parish PDF slices (do not revert parish pages to fake mega-only PDFs) | `ocr/parish_pages.py` |

## How to close an item

1. Change the **canonical generator** (not only a one-off HTML file).
2. Regenerate the live diocese pages (Raphoe, Derry, Down & Connor) so parishpress.ie gets the fix after deploy.
3. Tick the box, set status to `done`, and note the PR / date verified.

---

## Current checklist

| Status | Added | Item | Where in the code |
|--------|--------|------|-------------------|
| done | 2026-08-20 | Living backlog file (this document) so website/OCR requests cannot be memory-holed | `docs/WEBSITE_OCR_BACKLOG.md` |
| done | 2026-08-20 | Cursor rule: read this file first; 850/450; new-tab links; mega PDF stays on | `.cursor/rules/website-ocr-backlog.mdc` |
| done | 2026-08-20 | Short pointer in the agent guide | `AGENTS.md` (Website / OCR backlog) |
| done | 2026-08-20 | Visible **parish name header** on every parish OCR block (name + date if known). Not an accordion. | `ocr/bulletin_layout.py` (`render_parish_masthead`, `structure_ocr_html`); CSS in `ocr_reading_css()` |
| done | 2026-08-20 | Promote existing bulletin topic lines to real `h2`/`h3` (Mass times, Anniversaries / RIP / deceased, Community / notices, Fundraising / bingo / events, Contact). Do not invent text. Keep Irish as Irish. | `ocr/bulletin_layout.py`; applied from `ocr/convert_bulletin.py` (`render_markdown_lines`) and `prepare_ocr_fragment` |
| done | 2026-08-20 | Readable OCR measure: larger body type, line-height ~1.65, space after headings, max-width ~72ch, soft stone paper (not harsh black-on-white), mobile wrap | `ocr_reading_css()` in `ocr/generate_bulletin_pages.py`; mirrored in `ocr/convert_bulletin.py` `CSS` |
| done | 2026-08-20 | Mega PDF parish URL links at the top of each parish must **work** and open in a **new tab** (PDF.js was painting canvases only, so annotations were dead) | `harvester/stitcher.py` (`_build_parish_header_pdf` `linkURL` + `newWindow=True`); `docs/assets/pdf-inpage-viewer.js` annotation overlay |
| done | 2026-08-20 | Desktop 850px min-height for PDF **and** OCR in the canonical generator; tablet/phone ~450px. Regenerated live diocese HTML so harvest cannot drop it. | `render_bulletin_viewer_shell`; tests in `tests/test_ocr_bulletin_pages.py`, `tests/test_page_renderer.py`, `tests/test_site_builder.py` |
| done | 2026-08-20 | Parish / diocese HTML links already use `target="_blank"` `rel="noopener noreferrer"` | `render_bulletin_viewer_shell`, `render_parish_link_grid`, `ocr/parish_pages.py` |
| locked | 2026-08-20 | Mega PDF generation stays on — do not disable `HARVEST_MEGA_PDF` | `.github/workflows/harvest.yml`, `main.py` (single-parish skip is intentional) |

Status values: `todo` · `doing` · `done` · `locked` (must not be undone) · `parked`

---

## Still open (do not pretend these are finished)

- [ ] **doing** · 2026-08-21 · Gortahork (`gort-a-choirce`) OCR empty — mega page 14 was banner-only (Irish image body never OCR'd). Fill sparse mega pages from the mega PDF image and slice by `pages.json` / `Page N`. Keep Irish as Irish. **Leave open until verified on live** https://www.parishpress.ie/parishes/raphoe/gort-a-choirce.html · `ocr/sparse_page_ocr.py`, `ocr/parish_splitter.py`, `ocr/parish_pages.py`
- [x] **done** · 2026-08-27 · Keep small megas **from now on**. On `main` after [#142](https://github.com/Raphoe-Diocese/parish_harvester/pull/142) `7c2728de`: harvest requires `gs --version`; stitcher compresses; OCR/Pages keep the smaller committed file. Live HEAD still Raphoe **6.1 MB**. First Sunday harvest still to watch. · `harvest.yml`, `ocr-bulletin.yml`, `deploy-pages.yml`
- [ ] **doing** · 2026-08-26 · Phone Open PDF. Same-tab Mega PDF is in [#139](https://github.com/Raphoe-Diocese/parish_harvester/pull/139). Do not mark done until Frank opens a mega PDF on his phone. · `docs/assets/pdf-inpage-viewer.js`, `harvester/site_builder.py`
- [ ] **doing** · 2026-08-27 · Phone first page: stream/Range **on** (same as desktop) so page 1 can show before the whole 6.1 MB arrives. Fallback still does a full-file load if Range fails. Do not mark done until live Pages + Frank sees it on a phone. · `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-27 · Phone mega still **ages** (Frank 27/08 18:58, still ~20s). Live Raphoe HEAD **5.55 MB** linearized — that file is still a 20s phone pull. Next: do not auto-start PDF.js on phones; `/screen` shrink if still too big after tap. Do not mark done until Frank’s phone is quicker. · `docs/assets/pdf-inpage-viewer.js`, `harvester/pdf_compress.py`
- [ ] **doing** · 2026-08-27 · Frank **go**: delete **Show PDF**; load PDF.js from parishpress `/assets/`; hardwire PDF **and** OCR 850px PC / 450px phone. Do not mark done until live phone page 1 is a few seconds and both boxes stay locked after Ctrl+F5. · `docs/assets/pdf-inpage-viewer.js`, `ocr/generate_bulletin_pages.py`
- [ ] **doing** · 2026-08-27 · Homepage **Mega PDF** is fast and readable (real file). **Open bulletin** is slow and unreadable because the diocese page draws PDF.js in a 450px box. Phone/mobile: do **not** run PDF.js; the PDF box is a same-tab link to the mega file (same path as Mega PDF). Desktop keeps PDF.js 850. Do not restore an iPhone iframe. Do not mark done until Frank’s phone. · `docs/assets/pdf-inpage-viewer.js`, `harvester/site_builder.py`
- [ ] **doing** · 2026-08-27 · Frank rejected **This week's PDF** (PR #149). Jump-to parish taps need `.pdf-inpage-pages` slots (`jumpPdf` + `parishPressScrollPdfToPage`). Put PDF.js back on the phone. Make type readable (paint width ≥720, dpr 2, overflow-x auto). Keep 450 box. No iPhone iframe. Do not mark done until Jump to works and the PDF is readable on his phone. · `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-27 · Frank: iframe loads faster but **PDF isn’t sized properly**. Live #150 paints phone pages at **720px** in a ~333px box (and can clip the right edge). Fit each page to the box width (`clientWidth`), overflow-x hidden, re-paint on resize. Keep Jump to / PDF.js / 850/450. No iPhone iframe. · `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-27 · Delete **Tap to enlarge** (broken, not needed). Frank 27/08. Do not mark done until live Raphoe JUMP TO row has no enlarge button. · `ocr/generate_bulletin_pages.py`, `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-27 · Desktop PDF 850px box. Live JS **does** lock `.pdf-inpage-pages` to 850px (proved 27/08 19:00 at 1920×1080) but wrap is `overflow:visible` and HTML still pins `?v=20260824a`, so an old cache shows the dump. Lock wrap overflow hidden + cache-bust. Do not mark done until Frank sees one framed 850px window. · `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-21 · Back room **View bulletin** opens this week’s scraped PDF: `Bulletins/<key>.pdf`, then `current/`/`stale/`, then the parishpress parish slice. No zip archives. Ship as Parish Trainer v1.61.12. · `extension/sidepanel.js`, `harvester/report.py`
- [ ] **doing** · 2026-08-21 · Trainer Guess must show the guessed URL + title and a **Save guessed link** / **Use this link** control that writes a real recipe step (download / goto / newest-picker). Top 3 candidates. Prefer newest Sunday; skip GDPR / privacy / wedding / Order of Mass. Do not hide Guess after refresh. Manifest footer must match. · `extension/content.js`, `extension/copilot.js`, `extension/manifest.json`
- [ ] **doing** · 2026-08-21 · Trainer ↔ GitHub sync: Problems/Directory load latest `parishes/parish_status.json` via commit SHA; Directory shows ok + UK date; Send & test waits for `last_tested_at` change · `extension/*`
- [ ] **doing** · 2026-08-22 · Add Clogher Diocese from official Expand-all directory (37 parishes; 21 harvestable after kitchen-sink + snapshot). Facebook stays clickable. Hunt command is `docs/DIOCESE_HUNT.md`. Do not mark the public Clogher page done until a harvest writes `docs/dioceses/clogher/` · `parishes/clogher_diocese_*`, `parishes/recipes/clogher/`, `parishes/dioceses.json`
- [ ] **todo** · 2026-08-27 · Clogher lists **Clontibret** under “no downloadable PDF”. That is a lie. The 23/08 file is on mucknoparish.ie (`F Clontibret Muckno Bulletin 23rd AUG 2026`). We skip Clontibret on purpose and harvest the same PDF once under Castleblayney. Page should say “same bulletin as Castleblayney”, not missing. Same pattern: Tyholland / Monaghan. Wait for Frank. · `parishes/recipes/clogher/clontibret.json`, Clogher missing list
- [ ] **doing** · 2026-08-28 · Stale / fake OCR audit. List is in [#152](https://github.com/Raphoe-Diocese/parish_harvester/pull/152) (check only). Harvest Sunday **23/08/2026**. Do not mark done — nothing on live pages was fixed. Claudy “fake” in that first pass is wrong: live newest file is `NEWSLETTER 9-8-26.docx` (real newsletter, old week). Antrim OCR “02/04/2017” is a leftover text layer; the picture is 30/08/2026. · `docs/WEBSITE_OCR_BACKLOG.md`, [#152](https://github.com/Raphoe-Diocese/parish_harvester/pull/152)
- [ ] **doing** · 2026-08-28 · Antrim (`antrimparish.com/bulletinpage/`): hidden PDF Embedder on www-static. Live 28/08: `30th-August-August-2026-1-1.pdf` HTTP 200 (345797 bytes), visual **30th August 2026**. GitHub Playwright times out on the listing. Recipe must predict www-static, never open `/bulletinpage/`. Page-1 text layer still says April 2017 — do not treat that leftover as the heading. · `parishes/recipes/down_and_connor/antrimparish.json`
- [ ] **doing** · 2026-08-28 · St Teresa’s (`stteresasparish.church/parish-news/`): newest post is two page images for **Sunday 30th August 2026**. Trainer print_to_pdf on main will not stack them. Recipe must stay `wp_json_newest_post_images` + `image_stack` count=2. No bulletin for 23/08 (announcement slug). · `parishes/recipes/down_and_connor/stteresasparish.json`
- [ ] **doing** · 2026-08-28 · Frank: fix flagged broken bulletins; kitchen-sink each parish (batches of 3). Skip Carrick / Lisburn / Tyholland. Do not invent a this-week file. No mega download on the PC. · `parishes/recipes/`
- [ ] **doing** · 2026-08-28 · Ederney / Cúl Máine. Live page has **Sunday 23rd August 2026**. GitHub harvest **403** (Adobe/Fastly). No weekly PDF/JPG. Recipe already `print_to_pdf`. Leave on Problems as blocked. Do not retrain. Do not invent a PDF. · `parishes/recipes/clogher/ederney.json`
- [ ] **doing** · 2026-08-28 · Claudy content gap. Newest Word file is `NEWSLETTER 9-8-26.docx` (HTTP 200, heading 9/8/26). `23-8-26` and `16-8-26` are 404. [#153](https://github.com/Raphoe-Diocese/parish_harvester/pull/153) scrapes the listing without waiting for Google iframes — after merge expect **stale**, not ok. · `parishes/recipes/derry/parishofclaudy.json`
- [ ] **doing** · 2026-08-28 · Ardstraw East form skip merged [#154](https://github.com/Raphoe-Diocese/parish_harvester/pull/154). Newest real newsletter is **5 July 2026**. Do not call ok until a harvest shows **stale** on that July file. · `parishes/recipes/derry/parishofardstraweast.json`
- [x] **done** · 2026-08-23 · OCR search bar sticks only after a search term is typed (`.ocr-sticky-chrome.is-searching`). Verified live 23/08/2026 on https://www.parishpress.ie/bulletins/derry-2026-08-21-ocr.html after PR #88 + Pages: HTML has `is-searching` + `syncOcrSearchSticky` · `harvester/site_chrome.py`, `docs/assets/pdf-inpage-viewer.js`
- [x] **done** · 2026-08-22 · Homepage: one compact row of live dioceses with cathedral photos, short welcome, no junk footer. Card title **Down & Connor Diocese** stays on one line (`h2.is-long`). Verified live 22/08/2026 on https://www.parishpress.ie/ after PR #83 + Pages deploy · `harvester/site_builder.py` `_landing_page`
- [x] **done** · 2026-08-22 · Parish Press favicon (teal PP logo) on generated pages. Verified live 22/08/2026: `https://www.parishpress.ie/favicon.png` HTTP 200 (`image/png`, 6867 bytes) and homepage has `href="/favicon.png"` · `harvester/site_chrome.py` `favicon_link_tags`, `docs/favicon.png`
- [x] **done** · 2026-08-22 · Homepage Clogher card: status eyebrow stays on one line (`No data yet` + `.live-card-eyebrow { white-space: nowrap }`). Verified live 22/08/2026 on https://www.parishpress.ie/ after PR #85 + Pages run 32606594172. Old wrapping `No reliability data yet` is gone; more-dioceses note unchanged · `harvester/site_builder.py` `_status_label`
- [x] **done** · 2026-08-23 · Homepage cards show `Bulletins ready @ 16:00` plus a real count. Verified live 25/08/2026 on https://www.parishpress.ie/: Clogher **19/37**, Derry **26/31**, Down & Connor **32/56**, Raphoe **22/26**. Raphoe diocese page already lists missing (Gweedore, Kilbarron, Mevagh) and stale (Stranolar). Next harvest refreshes those numbers — it does not add this feature. Counts still include some old-body `ok` rows until the H1/H3 harvest. · `harvester/site_builder.py` `_live_card_ready_html` `_count_dot`
- [ ] **doing** · 2026-08-25 · Honest miss: H1/H3 harvest did **not** drop Raphoe July. Live OCR still `Sunday 19 July 2026`; status still `ok`. Same-line newsletter parser skipped a split heading. Adjacent-line heading PR [#138](https://github.com/Raphoe-Diocese/parish_harvester/pull/138) merged `23868416`. Raphoe harvest [32944718564](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32944718564) **heading checker worked** (`stale bulletin (2026-07-19)`) then **rescrape found current-week** and status stayed `ok`. Do not call Raphoe fixed. Next: stop Drive/static rescrape from treating an undated URL as this week. Also still `ok` with old bodies: Banagher 28/06, Melmount 12/07, Glenfin 16/08, Gortahork 16 Lúnasa, Randalstown 16/08. Limavady status is this week; live OCR page still 16/08. Do not call these fixed until a harvest + live page. · `harvester/bulletin_freshness.py` `extract_bulletin_date_from_text`
- [ ] **doing** · 2026-08-25 · Harvest [32852633310](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32852633310) finished 103 ok / 12 failed (89.6%). Limavady `23-8-26.pdf` exists; harvest hit **Total timeout** because urllib waits on IPv6/expired TLS — do **not** raise timeouts. Bake IPv4 + expired-cert HTTP into `_fetch_bytes_with_retries` — PR [#135](https://github.com/Raphoe-Diocese/parish_harvester/pull/135) merged `8f34165f`. Same hole: Newtownbutler, Claudy. Limavady harvest [32865595690](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32865595690) **ok** `23-8-26.pdf` (`parish_status` 25/08/2026 15:27 UTC). Recipe PRs: Derriaghy [#136](https://github.com/Raphoe-Diocese/parish_harvester/pull/136) (conflicts), Newtownbutler/Antrim/Loughshore [#137](https://github.com/Raphoe-Diocese/parish_harvester/pull/137). Content-gap/blocked stay: Bundoran Feb 2025, Ederney 403, Saint Malachy’s 6pp 2025, Greencastle/Long Tower disabled. Mega PDF stays on. · `harvester/replay.py` `_fetch_bytes_with_retries`
- [ ] **doing** · 2026-08-23 · Recipe success — Problems-tab hunt 24/08/2026. **Limavady recipe live** after PR [#132](https://github.com/Raphoe-Diocese/parish_harvester/pull/132) (`23-8-26.pdf` HEAD 200). **Kilmore recipe merged** PR [#133](https://github.com/Raphoe-Diocese/parish_harvester/pull/133) (`23rd_august_2026_combined-1.pdf` HEAD 200, listing shows 23rd August 2026) — **not live until next harvest**. Content-gap (no 23/08 file): Bangor 14/06, Malin April (status August URL is 404), Saint Malachy’s Feb 2025 6pp, Saint Anthony 09/08, Derriaghy 09/08, Stranorlar 28/06, Holy Cross (230826.pdf still 12/07 body), St Oliver 28/06, Hannahstown 07/06, Dunsford 05/07, St Patrick’s 05/07, Dromore June, Bundoran Feb 2025. Ederney harvest 403; this PC saw 404 on culmaine.co.uk/newsletter. Skip Carrick / Lisburn / Tyholland. · `parishes/recipes/`, `harvester/utils.py`, `harvester/replay.py`
- [ ] **todo** · 2026-08-20 · parishpress.ie — live DNS / Pages cutover when Frank is ready · `docs/PARISHPRESS_IE_MIGRATION.md`, `docs/DOMAIN_SETUP.md`
- [ ] **doing** · 2026-08-22 · Keep **this week only** on the public site and in the repo. Old dated `docs/bulletins/` pages and leftover PDFs go. This week’s mega PDFs stay. Frank asked again 22/08/2026 (space). · `harvester/retention.py`, `ocr/generate_bulletin_pages.py` `write_bulletins_index`
- [ ] **todo** · 2026-08-20 · Site look — modern pages **after** OCR/capture/recipes are reliable · `harvester/site_builder.py`, `docs/`
- [ ] **parked** · 2026-08-23 · Homepage: move “newsletters are posted after Sunday harvest” into the welcome. Cards show **count only** (`12/32 available` when known, `—/—` until then) + the green/amber/red dot. Do not use today’s date as the “fresh weekly” claim. Frank 23/08/2026 — discuss first, wait to implement · `harvester/site_builder.py` `_landing_page`
- [x] **done** · 2026-08-23 · OCR copies the PDF’s own text on born-digital pages (prefer embedded; vision only for image pages; still max ~26 then split). Verified live 23/08/2026 after PR #91 + Pages run 32637280999: https://www.parishpress.ie/parishes/down_and_connor/ballycastleparish-ocr.html has **Church Car Park** and **Saturday 22nd August**; the old **Saturday 2nd August** reading is gone · `ocr/text_extract.py` `ocr/bulletin_layout.py` `ocr/convert_bulletin.py` `ocr/parish_pages.py`
- [x] **done** · 2026-08-23 · Welcome: ongoing project; searchable text may be incomplete; confirm Mass times, names, and notices against the original PDF. Verified live 23/08/2026 on https://www.parishpress.ie/ after PR #91 + Pages run 32637280999 · `harvester/site_builder.py` `_landing_page`
- [x] **done** · 2026-08-23 · This week’s Ballycastle PDF (`23rd-August-2026.pdf`) on the live page. Verified 23/08/2026 after harvest 32639270521 + PR #92 + Pages run 32639731071: https://www.parishpress.ie/parishes/down_and_connor/ballycastleparish-ocr.html has **Enda Hill, R.I.P.**, Edna Hill thanks, Month’s Mind Sat 29th Aug 10am, Causeway Coast Peace Group. Dorothy McKinley is gone. Printed spelling kept (Enda / Edna) · `parishes/recipes/down_and_connor/ballycastleparish.json`

---

## Scale gameplan (parked — Frank 23/08/2026)

Do **not** start this until the locked OCR / Problems / recipe list is further on. This is the Ireland-wide expansion talk, written down so it is not memory-holed.

**Facts today (4 live dioceses)**

- Sunday harvest cron is **10:00 Irish**. Today’s full run (23/08/2026) ran about **70 minutes** (09:08–10:18 UTC).
- The harvest job **dies at 6 hours** (`timeout-minutes: 360`). A 12–15 hour run would be killed.
- One **full** harvest at a time. A **single-parish** Send & test can run beside it (different queue). Two diocese jobs in parallel would fight over `git push` / `report.json` — that is not built yet. The file already sketches the fix: one job per diocese writes an artifact, then a stitch job builds megas + status + pages.
- OCR is **one mega PDF per diocese**, then the text viewer is split. That is how tokens stay cheap. 24 megas/week is plausible; **700 separate OCR jobs/week is not**.
- GitHub already reports this repo at about **490 MB**. GitHub gets unhappy near **1 GB**. 700 parish PDFs **every week forever** will not fit. **This week only** is required.
- Parish pages did not vanish from the repo. They live under `docs/parishes/<diocese>/` and are linked from each **diocese** page A–Z, not from the homepage cards. A harvest that started on old code can overwrite those pages; that is the known clobber risk.

**Problems when we add the rest of Ireland**

- 12–15 hour harvests will hit the 6-hour kill switch.
- 16:00 Sunday as a “100% ready” clock will become a lie.
- Actions minutes on a **public** repo are free; the limit is time, git races, and OCR tokens — not a credit card.
- 600–700 public parish pages are fine **if** we keep only this week’s HTML + this week’s PDFs. They are not fine as a growing archive.

**What we will do later (not now)**

1. Split harvest: one GitHub job per diocese + one stitch job (already noted in `harvest.yml`).
2. Keep OCR on the mega PDF, not on each parish file.
3. Ship **this week only** (already parked).
4. When Frank says so: welcome-line + count-only cards (item above).
5. Put a clear “Parish pages” entry on each diocese screen so they are not only buried in the A–Z list.

---

## Harvest vs UI merge (do not panic)

A full harvest that **started** before a viewer-chrome merge (parish mastheads / 850px / new-tab) can commit and deploy `docs/dioceses/` from the old checkout and briefly overwrite live HTML. That is temporary.

`ocr-bulletin.yml` then checks out latest `main` (`ref: main`), runs `ocr/generate_bulletin_pages.py` (parish pages + dated viewers) and `harvester.site_builder.run()` (diocese `index.html` via `render_bulletin_viewer_shell` + `structure_ocr_html`), and restores the same files. Example: harvest [32384891762](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32384891762) started 2026-08-20 15:14 UTC on `ac41d567` (no `ocr/bulletin_layout.py`); after it finishes, OCR on current main restores #52 chrome.

Harvest.yml also refreshes viewer templates from `origin/main` before writing the docs snapshot, so a later in-flight UI merge is less likely to clobber.

---

## Verify after every harvest regenerate

Harvest rewrites `docs/dioceses/*/index.html` from `render_bulletin_viewer_shell`. After a harvest or `harvester.site_builder.run()`, confirm:

```bash
python -m pytest tests/test_ocr_bulletin_pages.py tests/test_bulletin_layout.py tests/test_page_renderer.py tests/test_site_builder.py -q
```

Spot-check generated CSS for:

- `min-height: 850px`, `height: auto`, and `overflow: visible` on the visible `.pdf-inpage-pages` and `#ocr-panel` (no inner scrollbar)
- no `overflow-y: auto` on `#ocr-panel` and no `overflow: auto` on `.pdf-inpage-pages`
- no `height: 85vh` clip on `.pdf-frame-wrap.is-native-pdf`
- `@media (max-width: 1024px)` with `min-height: 450px` and `height: auto` on those same visible boxes
- sticky search (`.ocr-sticky-chrome`) + back-to-top `#scroll-top-btn`
- `ocr-parish-masthead` / `ocr-parish-name` in the OCR panel
- `getAnnotations` + `target="_blank"` in `docs/assets/pdf-inpage-viewer.js`
