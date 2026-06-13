# AI Conversation Log — 2026-06-13: Full Repo Problems + Fix Plan

**Date:** 2026-06-13  
**Login:** @Frankytyrone  
**Repos:** raphoe working copy; GitHub `Raphoe-Diocese/parish_harvester` (workflows screenshot)

---

## Plain-English Summary

Franky asked for an honest inventory of everything broken, a plan to get the harvester working, analysis of `ardstraw.txt`, and updates to recipes/extension — while also saving all context for future AIs. He prefers the **archive bulletin layout** over the current **big bulletin** diocese page, finds **OCR abysmal**, and sees **GitHub Actions harvest workflows failing**.

---

## Problems identified (complete list)

### 1. Extension / Parish Trainer (v1.32.1 in browser)

| Problem | Example |
|---------|---------|
| UI overload — too many buttons | Clonmany screenshot |
| Follow-link loses recording on new tab | Multi-click recipes |
| Wrong PDF auto-pick | Ardstraw picked `DataEntryFormPdf.pdf` not May 2026 newsletter |
| Admin PDFs not filtered | Gift Aid, Standing Order, Data Entry forms score as PDFs |
| "May 2026" labels not parsed | Parish Messenger dated rows |
| Get a PDF shown first | User always uses Follow a link |
| Parish Messenger not recognised | Ardstraw, DMA, Culdaff family |

### 2. Recipes / harvester data

| Problem | Detail |
|---------|--------|
| `parishofardstraweast` recipe empty + `skip: true` | 11 consecutive failures |
| Many recipes in `unknown/` not `derry/` | Wrong diocese folder |
| `bulletin_urls` had only page URL for Ardstraw | No DDMMYY PDF evidence |
| Ballinascreen | Wix HTML needs `print_to_pdf`, not download |
| Bellaghy, Claudy, Aghyaran | Known bleed / menu issues from prior sessions |
| `ardstraw.txt` saved wrong | File is DMA/Dunboe HTML copy — not Ardstraw live DOM |

### 3. GitHub Actions / CI

| Problem | Detail |
|---------|--------|
| **Harvest Parish Bulletins** failing | Runs #1–3 on Raphoe repo |
| **release-extension.yml corrupted** | Second disabled workflow appended to same file — broke YAML |
| Workspace not a git clone locally | Changes not pushed unless Franky asks |

### 4. OCR / bulletin viewer layout

| Problem | Detail |
|---------|--------|
| Double-encoded entities | `St. Mary&amp;#x27;s` instead of apostrophe |
| Image markdown in OCR | `!img-0.jpeg!` in Down & Connor viewer |
| Franky prefers **archive** layout | `docs/bulletins/derry-2026-05-20.html` (paginated PDF + back link) |
| Current diocese page | `docs/dioceses/derry/index.html` — flat mega-PDF embed, worse UX |

### 5. Mega bulletin content

| Problem | Detail |
|---------|--------|
| Many parishes still `html_link` not real PDF | Links in mega PDF not bulletins |
| High failure count | `consecutive_failures.json` — many parishes 7–11 fails |

### 6. Process / memory

| Problem | Detail |
|---------|--------|
| Chat sessions lost | `ai_conversations/` + `ai/README.md` mitigate |
| Credit burn fear | Prefer rules over AI on every parish |

---

## Ardstraw / `ardstraw.txt` analysis

**Live site:** `http://parishofardstraweast.com/parishnews.html`  
**Family:** Parish Services / **Parish Messenger** (same as DMA, Culdaff, Carndonagh)

**Saved `ardstraw.txt` is wrong** — contains Dunboe/Macosquin HTML (duplicate of `dma parish.txt`). Newsletter list in Franky's screenshot only appears after Parish Messenger JavaScript runs.

**Bulletin pattern:** Pattern A `pdf/DDMMYY.pdf` after clicking **View Newsletter** or dated row ("May 2026 - Ardstraw East Parish").

**Extension bug:** When no URL dates found, picker offered `pdf/DataEntryFormPdf.pdf` from "New to the Parish" menu — admin form, not bulletin.

---

## Changes made this session (2026-06-13)

### Harvester / data
- `parishes/recipes/derry/parishofardstraweast.json` — proper Parish Messenger click recipe (removed skip)
- `parishes/derry_diocese_bulletin_urls.txt` — DDMMYY PDF evidence for Ardstraw
- `parishes/site_patterns.json` — `parish_messenger_embed` pattern
- `parishes/host_profiles.json` — longer wait for ardstraw, dmaparish, parishmessenger

### Extension v1.34.1
- Filter admin PDFs (`DataEntryForm`, GiftAid, etc.)
- Parse "May 2026" month+year in labels
- Detect `parish_messenger` page type
- Prefer bulletin-looking links in pick-newest

### OCR
- `ocr/generate_bulletin_pages.py` — repeat `html.unescape` to fix `&amp;#x27;`

### CI
- `.github/workflows/release-extension.yml` — removed duplicate disabled workflow block

### Docs
- `ai_conversations/2026-06-13-dma-parish-dates-and-extension-roadmap.md`
- This file

---

## Recommended next steps (priority)

1. **Push to GitHub** when Franky approves (clone repo, copy changes, commit).
2. **Re-run Harvest workflow** on Raphoe repo after push — verify pytest + harvest.
3. **Reload extension v1.34.1** — test Ardstraw: should detect Parish Messenger, ignore Data Entry PDF.
4. **Regenerate OCR pages** — apostrophes should render correctly on next OCR workflow run.
5. **Layout:** Point `docs/dioceses/derry/index.html` at archive template (paginated viewer) — needs `generate_bulletin_pages.py` or manual template swap.
6. **Ballinascreen** harvester: `copy-of-` URL fallback (harvester only).
7. **Batch-fix Parish Messenger family** — apply ardstraw recipe pattern to ~15 DDMMYY parishes.

---

## Extension future (credit-conscious)

See `2026-06-13-dma-parish-dates-and-extension-roadmap.md` — rule-based patterns first, AI only on "I'm stuck".

---

## Hand-off for next AI

- Franky on extension **v1.32.1** until reload from `extension/` folder.
- Do not claim GitHub push done until verified.
- `ardstraw.txt` ≠ live Ardstraw page — do not trust saved HTML for link extraction.
- User prefers archive bulletin UX over mega-PDF diocese index.
