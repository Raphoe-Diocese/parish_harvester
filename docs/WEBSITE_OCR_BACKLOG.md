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
| Sticky OCR search stays **outside** `#ocr-panel`; page **↑** `#scroll-top-btn` jumps to the top of the page | `harvester/site_chrome.py`, viewer shell |
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
- [ ] **doing** · 2026-08-22 · Homepage Clogher card: “No reliability data yet” wraps and breaks the four-card line-up. Keep the status eyebrow on one line (`No data yet` + `.live-card-eyebrow { white-space: nowrap }`). Leave open until verified on live https://www.parishpress.ie/ · harvester/site_builder.py _status_label
- [ ] **todo** · 2026-08-20 · Recipe success — one parish at a time (A–Z repair with proof packs) · `parishes/recipes/`, Problems tab
- [ ] **todo** · 2026-08-20 · parishpress.ie — live DNS / Pages cutover when Frank is ready · `docs/PARISHPRESS_IE_MIGRATION.md`, `docs/DOMAIN_SETUP.md`
- [ ] **todo** · 2026-08-20 · Site look — modern pages **after** OCR/capture/recipes are reliable · `harvester/site_builder.py`, `docs/`
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
- `.ocr-sticky-chrome { position: sticky; top: 0 }` **outside** `#ocr-panel`, and `#scroll-top-btn` (page top)
- `/assets/pdf-inpage-viewer.js?v=20260822c` (cache-bust)
- `ocr-parish-masthead` / `ocr-parish-name` in the OCR panel
- `getAnnotations` + `target="_blank"` in `docs/assets/pdf-inpage-viewer.js`
