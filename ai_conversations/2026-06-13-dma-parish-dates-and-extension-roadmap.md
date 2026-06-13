# AI Conversation Log — 2026-06-13: DMA Parish Dates + Extension Roadmap

**Date:** 2026-06-13  
**Login:** @Frankytyrone  
**Repo:** parish_harvester (raphoe working copy)  
**Source file analysed:** `parish_harvester-main raphoe/dma parish.txt`  
**Extension:** NO changes made this session (Franky asked to stop ext edits to save credits)

---

## Plain-English Summary

Franky asked to:

1. Read `dma parish.txt` and work out bulletin **dates** so the same logic helps **other parishes**.
2. **Not** change the extension (credit / stability concerns).
3. Save this discussion for the next AI (`ai/` + `ai_conversations/`).
4. Explain **future extension plans** — smarter, flexible, able to find PDFs, turn HTML/images into PDFs, suited to amateur volunteer-run sites.

---

## What `dma parish.txt` actually is

Saved HTML from **DMA Parish** website — full name on the page:

> **Parish of Dunboe, Macosquin, Aghadowey** (Coleraine area, Derry Diocese)  
> URL: `https://dmaparish.com/parishnews.html`  
> Hosted by **parishservices.co** (footer: “Site developed by parishservices.co”)

This is **not** Clonmany. Clonmany (`clonmanyparish.ie`) is a different site type (WordPress + embedded viewer). Franky’s Clonmany screenshot and DMA are separate problems.

---

## Key technical finding — Parish Messenger embed

The bulletin links are **not** in the static HTML Franky saved. They are injected by JavaScript:

```html
<script src="https://theparishmessenger.com/xlaabsolutenm.aspx?z=812&tag=ColeraineParishNews"></script>
```

- **theparishmessenger.com** = third-party bulletin widget (Parish Services ecosystem).
- `z=812` = site/account id on their system.
- `tag=ColeraineParishNews` = which widget block (news vs footer services).

When you “Save page as HTML”, you get the shell (menus, banners) but **not** the live “View Newsletter” link. The harvester must either:

- Run a real browser (Playwright) and wait for the script, **or**
- Use a trained recipe that clicks `View Newsletter` after the widget loads.

---

## Date pattern for DMA (and many Derry parishes)

### Pattern A — `DDMMYY` in `/pdf/` filenames

Documented in `parishes/derry_diocese_bulletin_urls.txt` and `parishes/NEW_DIOCESE_TEMPLATE.md`.

| Filename | Decoded date | Day of week |
|----------|--------------|-------------|
| `pdf/120426.pdf` | **12 April 2026** | Sunday ✓ |
| `pdf/220326.pdf` | **22 March 2026** | Sunday ✓ |
| `pdf/170526.pdf` (in recipe) | **17 May 2026** | Sunday ✓ |

**Format:** `DD` + `MM` + `YY` (two-digit year).  
**Example:** `120426` → day 12, month 04, year 26 → 12 Apr 2026.

### How Sunday harvesting uses this

The harvester (`harvester/utils.py` → `rewrite_date_url`) can take a known URL like:

`https://dmaparish.com/pdf/170526.pdf`

and rewrite the six digits to **next Sunday’s** date, e.g. for 14 June 2026 → `140626.pdf`.

No AI needed — pure date maths on the filename.

### Current recipe (`parishes/recipes/unknown/dmaparish.json`)

```json
{
  "start_url": "https://dmaparish.com/parishnews.html",
  "steps": [
    { "action": "goto", "url": "https://dmaparish.com/parishnews.html" },
    {
      "action": "click",
      "selector": "a:has-text(\"View Newsletter\")",
      "href": "pdf/170526.pdf",
      "text": "View Newsletter"
    }
  ]
}
```

**Missing terminal step:** recipe records the click but may not have explicit `download` with captured PDF URL. Harvester may still resolve PDF after click — verify on next harvest run.

**Diocese field empty** — should be `derry` when pushed properly.

---

## Parishes that share the DMA pattern (learn once, reuse many)

Same **Pattern A** (`/pdf/DDMMYY.pdf`) + often same **“View Newsletter”** click + often **parishservices.co** / Parish Messenger:

| Parish key | Example PDF URLs in evidence file |
|------------|-----------------------------------|
| dmaparish | `pdf/120426.pdf`, `pdf/220326.pdf` |
| buncranaparish | `pdf/050426.pdf`, `pdf/220326.pdf` |
| carndonaghparish | `pdf/120426.pdf`, `pdf/290326.pdf` |
| castledergparish | `pdf/120426.pdf`, `pdf/290326.pdf` |
| culdaffparish | `pdf/120426.pdf`, `pdf/050426.pdf` |
| culmoreparish | `pdf/120426.pdf`, `pdf/290326.pdf` |
| drumquinparish | `pdf/120426.pdf`, `pdf/050426.pdf` |
| parishofdungiven | `pdf/120426.pdf`, `pdf/050426.pdf` |
| errigalparish | `pdf/120426.pdf`, `pdf/290326.pdf` |
| fahanparish | `pdf/120426.pdf`, `pdf/050426.pdf` |
| parishofkilrea | `pdf/120426.pdf`, `pdf/050426.pdf` |
| leckpatrickparish | `pdf/120426.pdf`, `pdf/050426.pdf` |
| magheraparishderry | `pdf/050426.pdf`, `pdf/290326.pdf` |
| movilleparish | `pdf/120426.pdf` |
| steugenescathedral | `pdf/120426.pdf` |

**Suggested new `site_patterns.json` entry (harvester data only — not extension code):**

```json
"parish_messenger_ddmmyy+click_view_newsletter": {
  "page_type": "parish_messenger_embed",
  "recipe_flow": "wait_click_view_newsletter_then_pdf",
  "label": "Parish Services / Parish Messenger widget",
  "advice": "Open parish news page → wait for View Newsletter → click → PDF is pdf/DDMMYY.pdf. Sunday URL can be predicted from last known filename.",
  "example_parishes": ["dmaparish", "culdaffparish", "carndonaghparish"],
  "success_count": 0
}
```

---

## Clonmany contrast (from Franky’s screenshot — different pattern)

| | DMA / Parish Messenger | Clonmany |
|--|------------------------|----------|
| Host | parishservices.co | WordPress |
| Bulletin | PDF via widget link | Embedded frame / viewer |
| Date in URL | `pdf/DDMMYY.pdf` | `wp-content/uploads/YYYY/MM/YYYY-MM-DD.pdf` (Pattern C) |
| Recipe | 1 click “View Newsletter” | Multi-click: Newsletter → Current Newsletter → frame |
| Extension pain | Widget not in saved HTML | Follow-link + new tab + iframe |

Evidence:

```
https://clonmanyparish.ie/wp-content/uploads/2026/04/2026-04-12.pdf  → 12 Apr 2026 (Sunday)
https://clonmanyparish.ie/wp-content/uploads/2026/04/2026-04-05.pdf  → 5 Apr 2026 (Sunday)
```

---

## Ballinascreen (already documented elsewhere)

Wix HTML — **no PDF file**. Bulletin **is** the web page. Harvester uses `print_to_pdf`, not a download link. See `ballinascreen-dates.txt` / `ballinascreen-dates-2025.txt` in raphoe folder.

---

## Decisions made this session

| Decision | Reason |
|----------|--------|
| **No extension code changes** | Franky: credit cost + fear of breaking v1.32.1 workflow |
| **Document DMA + Parish Messenger pattern** | Teaches harvester + future ext without coding |
| **Save under `ai_conversations/` + `ai/README.md`** | Persistent memory per AGENTS.md |
| **No GitHub push** | Not requested |

---

## Open backlog (priority order)

### A — Harvester (no extension)

1. Add `parish_messenger_embed` pattern to `site_patterns.json` when a recipe is confirmed working.
2. Fix `dmaparish.json`: add `diocese: "derry"`, ensure terminal `download` step with `captured_url` or URL pattern.
3. Parish Messenger hosts: add **wait** step or host profile (`parishes/host_profiles.json`) for `theparishmessenger.com` script load.
4. Ballinascreen: `copy-of-` URL fallback + Saturday outlier (from prior session).
5. Push to GitHub when Franky says go (workspace still not a git clone).

### B — Extension (only when Franky approves reload)

Local code may include **v1.34.0** changes from prior session (recording persistence, link-first UI). **Franky is still on v1.32.1 in browser** until he reloads unpacked extension.

Do **not** touch extension until Franky clears it.

### C — Credit-conscious “smart” strategy

Franky does **not** want AI burning credits on every parish. Preferred order:

1. **Rules** — date formats, host fingerprints, `site_patterns.json`
2. **One human-trained recipe** per pattern family
3. **Harvester replay** — Playwright does the heavy lifting (PDF download, print_to_pdf, image→PDF)
4. **AI last** — only when stuck, optional, user-triggered

---

## Future extension plans (roadmap — flexible, volunteer-site friendly)

Goal: **recipe maker for 1000+ amateur parish sites**, not an AI chatbot on every page.

### Phase 1 — Reliable trainer (mostly done / in progress)

- **Link-first workflow** — most parishes need 2–3 menu clicks before the bulletin appears.
- **Recording survives page changes** — steps saved in browser storage; toolbar follows new tabs (v1.34 local).
- **One screen, one next action** — not eight buttons at once.
- **Steps list always visible** while recording.

### Phase 2 — Rule-based “savvy” (no AI credits)

| Site type | Extension detects | User action | Harvester finishes |
|-----------|-------------------|-------------|-------------------|
| Direct PDF | URL ends `.pdf` | Save PDF | Download |
| PDF list / DDMMYY | Links like `pdf/120426.pdf` | Pick newest / follow link | Date rewrite for Sunday |
| Parish Messenger | Script from `theparishmessenger.com` | Wait → View Newsletter | Download PDF |
| WordPress PDF embed | `pdfemb` classes | Pick date card | Download |
| iframe / viewer | PDF inside frame (Clonmany) | Pick frame | Download from frame src |
| Wix / HTML bulletin | No PDF, page is the bulletin | Save page as PDF | `print_to_pdf` in harvester |
| Image newsletter | Large images on page | Pick / crop image | Image → PDF pipeline |
| Multi-page images | Several bulletin JPGs | Pick all | Stitch to one PDF |

Detection lives in **`pattern_library.js`** + **`site_patterns.json`** (learned from successful pushes). **Not** Gemini on every click.

### Phase 3 — “Apply similar recipe” button

When extension fingerprints a page as e.g. `parish_messenger_embed`:

- Show: *“This looks like Culdaff / DMA — apply that recipe?”*
- Pre-fill steps; user confirms or tweaks one click.

### Phase 4 — Harvester-side intelligence (extension stays thin)

Extension **records** steps; harvester **executes** smart fallbacks:

- HTML page → Playwright print to PDF (already in `harvester/fetcher.py`)
- Images → multi-page PDF (bundle B, May 2026)
- URL date prediction for Sunday (`rewrite_date_url`)
- Host-specific waits (`host_profiles.json`)

### Phase 5 — Optional AI (stuck button only)

- User clicks **“I'm stuck”** → one short AI call with page context.
- Successful fixes saved to `site_patterns.json` so AI is **not** needed next time.
- **No** background AI on every parish (Franky’s budget rule).

### Phase 6 — Bulletin week verification (harvester)

- After download: check filename date or OCR first line for “Sunday …”
- Flag wrong week in manifest / operator console — not hidden AI cost.

---

## What the extension should NOT become

- A chatbot on every page (credit burn, confusion).
- Auto-changing its own code mid-session.
- Replacing simple recipes with “smart extract” guesses.
- Promising AI magic for volunteer sites that just need **click → click → PDF**.

---

## Files referenced (not modified this session)

- `parish_harvester-main raphoe/dma parish.txt`
- `parishes/recipes/unknown/dmaparish.json`
- `parishes/recipes/unknown/clonmanyparish.json`
- `parishes/derry_diocese_bulletin_urls.txt`
- `parishes/site_patterns.json`
- `harvester/utils.py` (Pattern A date rewrite)
- `ai_conversations/AGENTS.md`

---

## Hand-off note for next AI

1. Read this file + `AGENTS.md` + prior `2026-06-13-extension-*` logs.
2. **Do not edit extension** unless Franky explicitly says reload / update.
3. Next **harvester-only** wins: Parish Messenger wait profile, `dmaparish` recipe terminal step, `site_patterns` entry for `parish_messenger_embed`.
4. Franky uses **`py`** not `python` on Windows.
5. Clonmany = iframe + click chain. DMA = Parish Messenger + DDMMYY PDF. Ballinascreen = Wix HTML print. Three different patterns — do not mix recipes.

---

## Related Cursor transcript

Parent chat: `7504fc81-71fe-451f-84d3-5a2846bbb33a` (extension usability, GitHub push question, DMA analysis).
