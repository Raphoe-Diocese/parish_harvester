# AI Conversation Log — 2026-06-13: Extension Load Fixes (Both Repos Compared)

**Date:** 2026-06-13  
**Login:** @Frankytyrone  
**Repo:** raphoe/parish_harvester (newer copy)  
**Compare folder:** `harvester compare repos` on Desktop (raphoe + frankytyrone side by side)

---

## Plain-English Summary

Franky compared two local copies of parish_harvester:

1. **frankytyrone** (older) — Brave/Chrome refused to load the extension at all.
2. **raphoe** (newer) — Extension loaded, but the floating toolbar did not work on parish pages.

This session diagnosed both problems and applied fixes in the local compare folder.

---

## Problems Found

### Problem 1 — frankytyrone: "Manifest is not valid JSON"

**Error shown in Brave:**
```
Manifest is not valid JSON. EOF while parsing a string at line 39 column 0
Could not load manifest.
```

**Root cause:** `extension/manifest.json` had a corrupted `"key"` field. The base64 string was cut off mid-way and literally ended with `[...]`, so the JSON string was never closed. Chrome cannot parse the file.

**Fix applied:**
- Removed the broken `"key"` field entirely (matches `SECURITY.md` guidance and the working raphoe manifest).
- Bumped version to **1.30.111**.
- Updated `background.js` inject list to include `click-chain.js` (was missing from on-demand injection).

**Files touched:**
- `extension/manifest.json`
- `extension/background.js`

---

### Problem 2 — raphoe: loads but toolbar broken

**Root cause (critical):** `extension/content.js` had a **syntax error** from a bad merge when the Smart Extract feature was added (~lines 3513–3537). Example of corrupted line:
```
showStatus(`❌ ${result.error 🆓 Smart Extract (FREE)";
```
That invalid JavaScript prevents the entire content script from running, so no floating toolbar appears on parish sites even though the extension icon loads fine.

**Secondary issue:** The Smart Agent JS files in `extension/agents/` were never listed in `manifest.json`, so even after syntax repair the **🆓 Smart Extract (FREE)** button would have thrown `smartExtractBulletin is not defined`.

**Fixes applied:**
1. Repaired the Smart Extract button handler (proper `else`, `catch`, `finally` blocks).
2. Removed duplicate/corrupted code fragments from the bad merge.
3. Fixed CSS typo in `aiResultBox` (`solid#374151` → `solid #374151`).
4. Wired `freeNotice` + `smartExtractBtn` into `aiSection` correctly.
5. Added all agent scripts to `manifest.json` content_scripts (before `content.js`).
6. Updated `background.js` on-demand injection to match manifest script list.
7. Bumped version to **1.30.111**.

**Files touched:**
- `extension/content.js`
- `extension/manifest.json`
- `extension/background.js`

---

## Decisions Made

1. **Remove extension key from manifest** rather than try to reconstruct the truncated base64 — key rotation is already flagged in `SECURITY.md`; local dev does not need a pinned extension ID.
2. **raphoe is the lead repo** for Smart Agent work; frankytyrone copy stays simpler (no `agents/` folder).
3. **Version 1.30.111** in both local copies so Franky can tell which build is loaded after reload.

---

## Standing Requests / Open Backlog

### From previous sessions (still open)
- Restore/test Brave auto-update workflow fully
- Extension key rotation (store in GitHub Secrets, inject at release build time)
- Truthfulness bugs in extension (P0 audit items)
- Run full `pytest` suite after test directory move
- Feature bundles B–G, I, K from May 22 audit

### New from this session
- **Franky must reload both extensions** in `brave://extensions` after these fixes
- **Test on a real parish website** (http/https) — toolbar should appear bottom-right
- **raphoe only:** add FREE Mistral API key in popup settings before using Smart Extract
- **raphoe only:** Smart Agent still needs real-world testing on 1000+ parish sites
- Decide whether to merge raphoe fixes back into the main GitHub `Frankytyrone/parish_harvester` repo

---

## How Franky Should Test (step by step)

### frankytyrone copy
1. Open Brave → `brave://extensions`
2. Remove the old broken Parish Trainer entry if still showing an error
3. Click **Load unpacked** → select:
   `Desktop\harvester compare repos\parish_harvester-main frankytyrone\parish_harvester-main\extension`
4. Confirm version **1.30.111** with no manifest error
5. Open any parish website → floating **Parish Trainer** toolbar should appear

### raphoe copy (newer)
1. Same steps but folder:
   `Desktop\harvester compare repos\parish_harvester-main raphoe\parish_harvester-main\extension`
2. Confirm version **1.30.111**
3. Open a parish website → toolbar should appear
4. Optional: Popup → save Mistral API key (free at console.mistral.ai) → try **🆓 Smart Extract (FREE)**

### If still broken
1. Open popup → **📋 Copy diagnostic info** → paste to next AI session
2. On the parish page press F12 → Console tab → look for red errors mentioning `content.js`

---

## Hand-off Note to Next AI

1. **Verify Franky actually reloaded** — fixes are only on disk until extension is refreshed in Brave.
2. **frankytyrone manifest** — do NOT re-add a partial `key` field; use release workflow + secrets if a stable extension ID is needed.
3. **raphoe content.js** — the Smart Extract block starts ~line 3408; do not duplicate it again when merging features.
4. **Compare repos folder** is a local workspace — changes here may not be pushed to GitHub unless Franky asks.
5. If toolbar still missing after reload, check: is the tab a real `http://` or `https://` page (not `chrome://` or PDF viewer)?

---

Contact: @Frankytyrone via GitHub  
Last updated: 2026-06-13
