# AI Conversation Log — 2026-06-13: Extension UX Fixes (Ardmore Parish)

**Date:** 2026-06-13  
**Login:** @Frankytyrone  
**Repo:** raphoe/parish_harvester

---

## Plain-English Summary

Franky reported three extension problems on `www.ardmoreparish.com`:

1. **"I need to click something first"** — expected the tool to follow him to the next page; it did not.
2. **Wrong bulletin auto-picks** — visible newest bulletin was "Sunday, 24th May 2026" but extension suggested old PDFs like `040126.pdf`.
3. **Smart Extract (FREE)** — does not understand what it does.

Extension v1.30.111 was loading correctly. GitHub PAT, Mistral, and Gemini keys all present.

---

## Root Causes

### Click mode
By design, pick-link mode **blocks** navigation (`preventDefault`) so the user can confirm the right link. User must manually go to next page after "Looks right" — confusing for beginners building multi-step recipes.

### Wrong bulletin picks
- Date in card header ("Sunday, 24th May 2026") is **above** the link; link text may just say "Read More".
- Scoring only used link text + URL, not parent card text.
- Filenames like `240526.pdf` (DDMMYY) were not parsed.
- Liturgical names ("Christmas", "Corpus Christi") scored approximate wrong dates.

### Smart Extract
Experimental one-click agent — tries patterns first, then FREE Mistral API. Not the same as guided recipe training.

---

## Fixes Applied (v1.30.112)

1. **New button: "🔗 Record & open link"** — saves click step AND navigates to linked page.
2. **Clearer pick-link message** — explains page won't move until user confirms.
3. **Better date detection:**
   - Reads date from parent card/heading near link
   - Parses `24th may 2026` (spaces)
   - Parses `pdf/240526.pdf` as DDMMYY

**Files touched:**
- `extension/content.js`
- `extension/manifest.json` (1.30.112)

---

## How Franky Should Use Ardmore (step by step)

1. Go to `http://www.ardmoreparish.com/news.html`
2. Click **🔗 I need to click something first**
3. Click the **Sunday, 24th May 2026** card link (or Read More under it)
4. Click **🔗 Record & open link** (NOT just "Looks right")
5. On the next page, if it's a PDF use **📄 Get a PDF**; if another click needed, repeat
6. When recipe steps look right → **⬆ Push Recipe to GitHub**

**Ignore wrong auto-picks** — use manual click flow above until v1.30.112 is reloaded.

**Smart Extract:** optional experiment; for training parishes use guided click flow above.

---

## Hand-off to Next AI

- Reload extension in Brave after pulling v1.30.112
- Existing recipe `parishes/recipes/derry/ardmoreparish.json` points to May 10 — may need update to May 24 flow
- Diagnostic dump copied from Copilot tab is normal but test on actual parish URL

---

Contact: @Frankytyrone  
Last updated: 2026-06-13
