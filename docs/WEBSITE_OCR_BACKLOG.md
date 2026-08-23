# Website / OCR living backlog

**Read this file before any website, OCR, diocese viewer, parish page, or mega-PDF viewer work.**

This is the single list. Do not create a second competing plan. Do not mark an item **done** unless you have verified it on **generated** HTML/CSS (the files under `docs/dioceses/`, `docs/parishes/`, `docs/bulletins/`, or a fresh `render_bulletin_viewer_shell` output) — changing Python alone is not enough. Harvest regenerate overwrites live HTML from the canonical generator.

**Do not lie about done.** Never tell Frank a website/OCR/viewer job is finished unless you have checked the **generated files that GitHub Pages deploys** (`docs/index.html`, `docs/dioceses/`, `docs/parishes/`) AND, after merge+Pages, the **live URL** (e.g. https://www.parishpress.ie/). Tests or Python-only edits are not enough. If it is not on the live page, say “not live yet”. Do not tick backlog items done without the live check.

Date format for new rows: `YYYY-MM-DD`. User-facing dates on the site stay **DD/MM/YYYY**.

## Locked product rules (do not “helpfully” undo)

| Rule | Where it lives |
|------|----------------|
| Mega PDF generation stays **on** (`HARVEST_MEGA_PDF=1`) | `.github/workflows/harvest.yml`, `AGENTS.md`, `DECISIONS_LOG.md` |
| Desktop PDF **and** OCR panels: **locked** `height` / `min-height` / `max-height` **850px**; extra content scrolls **inside** the box (`overflow: auto`). Not `height: auto`. Not `85vh`. | `ocr/generate_bulletin_pages.py` → `render_bulletin_viewer_shell`, `pdf_inpage_viewer_css()`; `docs/assets/pdf-inpage-viewer.js` `ensureStyles()` |
| Mobile/tablet (max-width 1024px): **locked 450px** (height + min + max), inner scroll | same function + JS, `@media (max-width: 1024px)` |
| Sticky OCR search stays **outside** `#ocr-panel`; page **↑** `#scroll-top-btn` shows when the **inner** PDF/OCR box or the page is scrolled, and jumps those boxes **and** the page to the top | `harvester/site_chrome.py` `scroll_top_js`, viewer shell, `docs/assets/pdf-inpage-viewer.js` `ensureScrollTop` |
| Parish / diocese outbound links open in a **new tab** (`target="_blank"` `rel="noopener noreferrer"`) | viewer shell, parish grids, `docs/assets/pdf-inpage-viewer.js` |
| OCR shows a **parish name header**, real **section headings**, professional spacing | `ocr/bulletin_layout.py`, `ocr_reading_css()` |
| Do not invent events or translate Irish/Gaeilge | `ocr/bulletin_layout.py`, `ocr/convert_bulletin.py` prompt |
| Keep real parish PDF slices (do not revert parish pages to fake mega-only PDFs) | `ocr/parish_pages.py` |
| **Do not lie about done.** Generated Pages files + live URL after merge+Pages. If it is not on the live page, say “not live yet”. | `AGENTS.md`, this file, `.cursor/rules/website-ocr-backlog.mdc` |

## How to close an item

1. Change the **canonical generator** (not only a one-off HTML file).
2. Regenerate the live diocese pages (Raphoe, Derry, Down & Connor) so parishpress.ie gets the fix after deploy.
3. Check the **generated files GitHub Pages deploys** (`docs/index.html`, `docs/dioceses/`, `docs/parishes/`).
4. After merge+Pages, check the **live URL**. If it is not on the live page, say “not live yet”. Do not tick done without that live check.
5. Tick the box, set status to `done`, and note the PR / date verified.

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
| done | 2026-08-20 | Desktop 850px / mobile 450px for PDF **and** OCR in the canonical generator. Regenerated live diocese HTML so harvest cannot drop it. Later locked as **fixed** visible boxes (not min-height-only growth) — see 2026-08-22 item. | `render_bulletin_viewer_shell`; tests in `tests/test_ocr_bulletin_pages.py`, `tests/test_page_renderer.py`, `tests/test_site_builder.py` |
| done | 2026-08-20 | Parish / diocese HTML links already use `target="_blank"` `rel="noopener noreferrer"` | `render_bulletin_viewer_shell`, `render_parish_link_grid`, `ocr/parish_pages.py` |
| locked | 2026-08-20 | Mega PDF generation stays on — do not disable `HARVEST_MEGA_PDF` | `.github/workflows/harvest.yml`, `main.py` (single-parish skip is intentional) |

Status values: `todo` · `doing` · `done` · `locked` (must not be undone) · `parked`

---

## Still open (do not pretend these are finished)

- [ ] **doing** · 2026-08-21 · Gortahork (`gort-a-choirce`) OCR empty — mega page 14 was banner-only (Irish image body never OCR'd). Fill sparse mega pages from the mega PDF image and slice by `pages.json` / `Page N`. Keep Irish as Irish. **Leave open until verified on live** https://www.parishpress.ie/parishes/raphoe/gort-a-choirce.html · `ocr/sparse_page_ocr.py`, `ocr/parish_splitter.py`, `ocr/parish_pages.py`
- [x] **done** · 2026-08-22 · Desktop 850px is a **fixed** visible box: `.pdf-inpage-pages` and `#ocr-panel` use `height: 850px; min-height: 850px; max-height: 850px; overflow: auto`. Extra PDF pages / OCR text scroll **inside** the box. Mobile/tablet `max-width: 1024px`: locked 450px the same way. Not `height: auto`, not `overflow: visible`, not `85vh`. Sticky search stays **outside** `#ocr-panel` (`.ocr-sticky-chrome`). Page **↑** `#scroll-top-btn` still jumps to the top of the page. Runtime `ensureStyles()` locks the same sizes with `!important` + cache-bust `?v=20260822c`. Verified on generated `docs/dioceses/raphoe/index.html`, `docs/dioceses/down-and-connor/index.html`, `docs/parishes/raphoe/gort-a-choirce.html`. · `render_bulletin_viewer_shell`, `pdf_inpage_viewer_css`, `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-21 · Back room **View bulletin** opens this week’s scraped PDF: `Bulletins/<key>.pdf`, then `current/`/`stale/`, then the parishpress parish slice. No zip archives. Ship as Parish Trainer v1.61.12. · `extension/sidepanel.js`, `harvester/report.py`
- [ ] **doing** · 2026-08-21 · Trainer Guess must show the guessed URL + title and a **Save guessed link** / **Use this link** control that writes a real recipe step (download / goto / newest-picker). Top 3 candidates. Prefer newest Sunday; skip GDPR / privacy / wedding / Order of Mass. Do not hide Guess after refresh. Manifest footer must match. · `extension/content.js`, `extension/copilot.js`, `extension/manifest.json`
- [ ] **doing** · 2026-08-21 · Trainer ↔ GitHub sync: Problems/Directory load latest `parishes/parish_status.json` via commit SHA; Directory shows ok + UK date; Send & test waits for `last_tested_at` change · `extension/*`
- [ ] **doing** · 2026-08-22 · Add Clogher Diocese from official Expand-all directory (37 parishes; 21 harvestable after kitchen-sink + snapshot). Facebook stays clickable. Hunt command is `docs/DIOCESE_HUNT.md`. Do not mark the public Clogher page done until a harvest writes `docs/dioceses/clogher/` · `parishes/clogher_diocese_*`, `parishes/recipes/clogher/`, `parishes/dioceses.json`
- [x] **done** · 2026-08-22 · Sticky OCR search (`.ocr-sticky-chrome { position: sticky; top: 0 }`) and `#scroll-top-btn` / `.scroll-top-btn` page-top jump. Search highlight uses `scrollIntoView({ block: 'start' })` so it sits below the sticky bar. If a parish page is missing the wrapper, `pdf-inpage-viewer.js` wraps zoom + search + tools. Verified on generated Raphoe diocese + Gortahork parish HTML. · `harvester/site_chrome.py`, `ocr/generate_bulletin_pages.py`, `docs/assets/pdf-inpage-viewer.js`
- [x] **done** · 2026-08-22 · Homepage: one compact row of live dioceses with cathedral photos, short welcome, no junk footer. Live-checked 22/08/2026 on https://www.parishpress.ie/ after PR #83 + Pages run 32603184327. · `harvester/site_builder.py` `_landing_page`
- [x] **done** · 2026-08-22 · Favicon on generated heads (`href="/favicon.png"` + apple-touch). Live-checked 22/08/2026: https://www.parishpress.ie/favicon.png HTTP 200 `image/png` 6867 bytes; homepage HTML has `href="/favicon.png"`. PR #83. · `harvester/site_chrome.py` `favicon_link_tags`, `harvester/site_builder.py`, `ocr/generate_bulletin_pages.py`
- [x] **done** · 2026-08-22 · Live diocese cards: one-line names (`Down & Connor Diocese`, `white-space: nowrap`, shrink `is-long` / `is-very-long`). Live-checked 22/08/2026 on https://www.parishpress.ie/: HTML has `Down &amp; Connor Diocese`, `white-space: nowrap`, `is-long`; does **not** have wrapping `Down and Connor Diocese`. PR #83. · `harvester/site_builder.py` `_live_card_heading_html`
- [x] **done** · 2026-08-22 · Homepage Clogher card: status eyebrow stays on one line (`No data yet` + `.live-card-eyebrow { white-space: nowrap }`). Verified live 23/08/2026 on https://www.parishpress.ie/ after PR #85 + Pages run 32606594172. Old wrapping text is gone; more-dioceses note unchanged · harvester/site_builder.py _status_label
- [ ] **doing** · 2026-08-23 · Killanny HTML /parish-bulletin harvested as stale (May 2021 text still live 23/08/2026). Do not skip; do not invent an August PDF. Leave open until a harvest writes parish_status for killanny · parishes/recipes/clogher/killanny.json
- [ ] **doing** · 2026-08-23 · Bundoran (Magh Ene / Clogher) content gap — **no this-week file**. Proved 23/08/2026 on magheneparish.ie: newest real newsletter is `https://magheneparish.ie/wp-content/uploads/2025/02/Parish_Newsletter_09.02.2025.pdf` HTTP 200 `application/pdf` 1029778 bytes, Last-Modified Sat 08 Feb 2025, PDF CreationDate `20250208102942`. Listing https://magheneparish.ie/newsletter/ HTTP 200 embeds that Feb 2025 file (page last modified 2025-02-08). Harvest mixed URL `http://magheneparish.ie/wp-content/uploads/2026/08/Parish_Newsletter_09.02.2025.pdf` is HTTP 404 this turn. `/wp-content/uploads/2026/08/` exists but is empty (month folder only). WP media after 2025-02-08: 0 items. Do not invent an August 2026 PDF. Do not change the recipe until a new file is on the site. · parishes/recipes/clogher/bundoran.json
- [ ] **doing** · 2026-08-23 · OCR search sticks only after a term is typed. Leave open until verified on live Derry text bulletin · harvester/site_chrome.py, docs/assets/pdf-inpage-viewer.js
- [ ] **doing** · 2026-08-23 · Homepage cards: drop reliability words; keep coloured dots; small semibold ⚪ Bulletins ready @ 16:00 plus real this-week N/M from `build_diocese_week_summary()` / `parish_status` (leave —/— only when total is 0). Colour the dot from ready/total. **Leave open until live** https://www.parishpress.ie/ shows N/M not —/—. · harvester/site_builder.py `_live_card_ready_html`, `run()`
- [ ] **doing** · 2026-08-23 · Faithful searchable OCR: prefer each PDF's own text layer (PyMuPDF + PyPDF2) on born-digital pages so vision cannot drop notices or turn 22nd → 2nd. fill_sparse only helped banner-only pages; `_ORDINAL_DUP_RE` ate `22nd`; parish-name banner swallow dropped long notices; `_is_url_only_line` deleted wrap leftovers (`recently.`); Windows NUL/lock writes skipped dioceses; `extract_ocr_fragment` missed standalone `.ocr-body`. Vision stays one pass per diocese (max ~26) then split — no second vision API. Leave open until verified on generated parish/diocese HTML **and** live parishpress.ie · `ocr/text_extract.py`, `ocr/convert_bulletin.py`, `ocr/sparse_page_ocr.py`, `ocr/bulletin_layout.py`, `ocr/parish_pages.py`, `ocr/generate_bulletin_pages.py`, `ocr/fidelity.py`
- [ ] **doing** · 2026-08-23 · Image bulletin OCR is smashed (Annagry first: `gi Teach`, mixed columns). Vision reads across a narrow left sidebar. Detect the real gutter, re-read left-then-right with tesseract, keep Irish as Irish. Do not mark done until live https://www.parishpress.ie/bulletins/raphoe-2026-08-23-ocr.html Annagry is readable (Mass times / names, not `gi Teach`). · `ocr/sparse_page_ocr.py`, `ocr/convert_bulletin.py`, `ocr/generate_bulletin_pages.py`
- [ ] **doing** · 2026-08-23 · Welcome honesty: homepage says Parish Press is an ongoing project and searchable text may be incomplete — confirm Mass times, names, and notices against the original PDF. **Leave open until live** https://www.parishpress.ie/ · `harvester/site_builder.py` `_landing_page`, `docs/index.html`
- [x] **done** · 2026-08-23 · Put Ballycastle’s 23/08 bulletin (Enda / Edna Hill, printed spelling kept) on the public Parish Press pages. Live-checked 23/08/2026: https://www.parishpress.ie/parishes/down_and_connor/ballycastleparish-ocr.html HTTP 200, `Last-Modified: Sun, 23 Aug 2026 21:27:12 GMT`, title `Ballycastle Text Bulletin — 23/08/2026`. Exact OCR strings: `Enda Hill, R.I.P.` and `The family of the late Edna Hill` (printed spelling kept; `Enda Hill` once, `Edna Hill` once). · `docs/parishes/down_and_connor/ballycastleparish.pdf`, `docs/mega_pdf/down_and_connor_mega_bulletin.pdf` pages 5–6, `docs/bulletins/down_and_connor-*.html`
- [ ] **doing** · 2026-08-23 · Recipe success — 13 Problems-tab parishes. **Clonleigh / Ballymoney / Glenariffe / Kincasslagh live ok**. **Castleblayney doing** (not done): scrape `/category/weekly-bulletin/` then the newest post PDF — do not mark done until a harvest on main writes `parish_status` ok. Kincasslagh harvest [32656116987](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32656116987) after PR #97: `outcome=ok`, url `https://www.kincasslagh.ie/app/uploads/2026/08/Newsletter-21st-Aug.pdf` (not `org_6-sep-15.pdf`). Content gap: Bangor 14/06, Dunsford 05/07, Holy Cross (230826.pdf still 12/07 body), Malin April (August URL 404), Hannahstown 07/06, Saint Malachy’s Feb 2025, St Oliver 28/06, St Patrick’s 05/07, Stranorlar 28/06, Bundoran 09/02/2025 (Aug-folder URL 404; only Feb 2025 file on magheneparish.ie). Skip Carrick / Lisburn / Tyholland. · `parishes/recipes/`, `harvester/replay.py`
- [ ] **parked** · 2026-08-23 · Clones this-week file is **real** (proved 23/08/2026): `https://www.clonesparish.com/uploads/downloads/Sunday%2023rd%20August%202026.pdf` HTTP 200, `application/pdf`, 417727 bytes. Homepage lists `/uploads/downloads/Sunday 23rd August 2026.pdf`. Harvest still said no dated PDF matching `uploads/downloads`. Do not start until Castleblayney is shipped. · `parishes/recipes/clogher/clones.json`
- [ ] **doing** · 2026-08-23 · Back to Top arrow (Divi-style ↑) must show when the reader scrolls the INNER PDF or OCR box, not only when the whole page scrolls. Frank’s 23/08/2026 screenshot at the bottom of Raphoe has no arrow. Click jumps that box (and the page) to the top. **Leave open until visible on live** https://www.parishpress.ie/dioceses/raphoe/ · `harvester/site_chrome.py` `scroll_top_js`, `docs/assets/pdf-inpage-viewer.js`
- [ ] **doing** · 2026-08-23 · Ballintra IS Drumholm. Do not list Ballintra as missing/Facebook-only when Drumholm has this week’s PDF. One A–Z name: Drumholm (Ballintra). **Leave open until live** Raphoe generated HTML shows the combined name. · `parishes/recipes/raphoe/ballintra.json`, stitcher missing page, parish grid
- [ ] **doing** · 2026-08-23 · Diocese page intro (not the last mega-PDF page): welcome; honest count “this week we found N of M bulletins”; never-publish / stale named separately; late-publish links. Professional tone. Do NOT invent bishop or office contacts — only details already in the repo or on the official diocese site (raphoediocese.ie). Move “Missing & Online-Only” off the bottom of the stitched PDF. **Leave open until live** https://www.parishpress.ie/dioceses/raphoe/ shows Welcome + N of M. · `harvester/stitcher.py`, `harvester/diocese_intro.py`, `ocr/generate_bulletin_pages.py` `render_bulletin_viewer_shell`
- [ ] **doing** · 2026-08-23 · A–Z jump list at the top of the PDF and OCR viewers so a reader can go straight to one parish. Same list as the working-parishes grid. Do not add a second competing menu. **Leave open until live** Raphoe HTML has `az-jump`. · `ocr/generate_bulletin_pages.py`
- [ ] **todo** · 2026-08-20 · parishpress.ie — live DNS / Pages cutover when Frank is ready · `docs/PARISHPRESS_IE_MIGRATION.md`, `docs/DOMAIN_SETUP.md`
- [ ] **todo** · 2026-08-20 · Site look — modern pages **after** OCR/capture/recipes are reliable · `harvester/site_builder.py`, `docs/`
- [ ] **parked** · 2026-08-23 · Longer diocese story — only if Frank asks again. No invented phones or emails.
- [ ] **parked** · 2026-07-30 · Remove bulletin archive entirely (`…/parish_harvester/bulletins/`) — do not start · `AGENTS.md` parked list

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

- `height: 850px`, `min-height: 850px`, and `max-height: 850px` on the visible `.pdf-inpage-pages` and `#ocr-panel` (not only the wrap)
- `overflow: auto` / `overflow-y: auto` on those boxes (content scrolls **inside** the 850px box)
- no `height: auto` and no `overflow: visible` on those visible boxes
- no `height: 85vh` clip on `.pdf-frame-wrap`
- `@media (max-width: 1024px)` with locked `height` / `min-height` / `max-height: 450px` and inner scroll on those same visible boxes
- `.ocr-sticky-chrome` **outside** `#ocr-panel` is `position: relative` until `.is-searching` (typed term), then `position: sticky; top: 0`. `#scroll-top-btn` listens to **inner** `.pdf-inpage-pages` / `#ocr-panel` scroll as well as the page
- `/assets/pdf-inpage-viewer.js?v=20260823t` (cache-bust; live HTML stays older until harvest/OCR regenerates)
- `ocr-parish-masthead` / `ocr-parish-name` in the OCR panel
- `getAnnotations` + `target="_blank"` in `docs/assets/pdf-inpage-viewer.js`
