# AI Conversation Log — 2026-06-13: Extension Deep Dive & Repo Comparison

**Date:** 2026-06-13  
**Login:** @Frankytyrone

---

## User's Real Goal

Extension as **recipe maker** for 1000+ amateur parish sites:
- Free/cheap AI scans pages
- Images → PDFs
- No stale bulletins in weekly harvest
- Handles: no SSL, slow loads, hidden PDFs in iframes, liturgical dates, guessable URL patterns

## Honest Verdict: Vision vs Reality

**Neither repo fully delivers the vision yet.** Both are ~60% there.

| What user wants | What exists today |
|-----------------|-------------------|
| Auto recipe from AI scan | Manual guided steps + Push to GitHub |
| Mistral builds recipe | Mistral only used in experimental Smart Extract + optional URL guesser |
| Gemini automates work | Gemini **advice only** — user was right to call it useless for automation |
| Image → PDF | Crop step in extension; conversion in Python OCR pipeline |
| No stale bulletins | Python harvester date math + `stale_bulletins.json` — not extension |
| iframe PDFs | Partial — "It's in a frame / viewer" + deep detect |

## What ACTUALLY Works (Recipe Making)

**The reliable path** (proven on Ardmore — user correctly picked `pdf/240526.pdf`):

1. **🔗 I need to click something first** → pick link
2. **👍 Looks right** OR **🔗 Record & open link** (v1.30.112+)
3. On PDF page: **📄 Get a PDF (recommended)**
4. Check **📋 Recipe Preview** shows steps
5. **⬆ Push Recipe to GitHub**

**Does NOT build recipes:**
- 🤖 AI Help (Gemini) — chat advice only
- 🤖 AI Training Mode + Ask AI — guesses one URL, user must confirm; does not save multi-step recipe
- 🆓 Smart Extract — experimental; **had bug** where "Save as Recipe" didn't add real steps (fixed v1.30.113)

## Repo Comparison

| | **raphoe (newer)** | **frankytyrone (older)** |
|--|--|--|
| Core recipe toolbar | ✅ Same | ✅ Same |
| Push Recipe to GitHub | ✅ | ✅ |
| Smart Extract agent | ✅ (experimental, buggy) | ❌ Not present |
| Python tests in `tests/` | ✅ | ❌ (root) |
| Logger, SECURITY.md, etc. | ✅ | Partial |
| Manifest loads | ✅ | Was broken (fixed) |
| content.js size | +9KB (smart agent code) | Smaller, simpler |

**Recommendation: Stay on raphoe**, but **ignore Smart Extract and Gemini** for now. Use guided recipe flow only. Raphoe has repo fixes + our UX patches. Frankytyrone is simpler but missing improvements and had corrupt manifest.

## Bug Fixed This Session

Smart Extract "💾 Save as Recipe" used `addSessionStep` with `recipeStep: null` — Push Recipe ignored it. Now uses `standaloneAddStep({ action: "download", url })`.

## Hand-off

- User still on v1.30.111 in screenshots — must reload for 1.30.113
- May 22 audit P0 truthfulness bugs still open in both repos
- Smart Agent needs weeks more work before replacing manual recipes

---

Contact: @Frankytyrone  
Last updated: 2026-06-13
