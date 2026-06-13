# OCR strategy — economical + maximum accuracy (26 dioceses)

**Date:** 2026-06-13  
**User:** Frankytyrone  
**Context:** Parish harvester OCR quality is poor; mass times and deceased names must be correct; ~$5 OpenAI credit; prefers free where quality allows.

---

## Scale (important — you are NOT OCR-ing 1000 parishes separately)

- **Harvest** may touch ~1000 parishes, but **OCR today runs on diocese mega-PDFs** (see `.github/workflows/ocr-bulletin.yml`): one stitched PDF per diocese per week.
- **~26 dioceses × ~30–40 pages/week ≈ 800–1,000 pages/week** → **~40,000–50,000 pages/year**.
- At **Mistral OCR batch pricing (~$1 per 1,000 pages)**, full-year bulk OCR is roughly **$40–50/year** — not thousands of dollars.
- Individual **Parish Messenger** PDFs (`pdf/DDMMYY.pdf`) are often **born-digital** (Word/InDesign export). **Free text extraction** can be 100% accurate with **zero AI cost** — we should try that **before** any vision OCR.

---

## Why current OCR looks "pants"

1. **Mega-PDF stitching** — many parishes in one file; headers, ads, and column breaks confuse layout.
2. **No born-digital pass** — `ocr/convert_bulletin.py` goes straight to Mistral → Gemini → OpenAI images; skips PyMuPDF/pypdf text extraction.
3. **Weak generic prompt** — `OCR_PROMPT` in `convert_bulletin.py` does not stress mass times, deceased names, or Irish orthography.
4. **Mistral markdown artefacts** — image placeholders like `!img-0.jpeg!` leak into HTML.
5. **Display bugs** — double-encoded entities (`&amp;#x27;`) in `generate_bulletin_pages.py` (partially fixed); looks like bad OCR but is HTML pipeline.
6. **Old Gemini fallback** — `gemini-1.5-flash` for vision OCR; newer models read small print better.
7. **150 DPI** — may be low for footnotes and dense timetable tables.

---

## Recommended tiered pipeline (economical + accurate)

| Tier | Method | Cost | When to use |
|------|--------|------|-------------|
| **0** | **PyMuPDF / pypdf text extract** | **Free** | PDF has selectable text (most Parish Messenger exports) |
| **1** | **Mistral OCR 3 batch** (`mistral-ocr-2512`) | **~$1/1k pages** | Scans, photos, image-only PDFs |
| **2** | **Correction pass (text only)** via `ai_router` | **Free** (Gemini → Groq → Mistral) | After OCR on **critical sections only** |
| **3** | **OpenAI gpt-4o-mini** | **$5 budget** | Pages where Tier 0–2 fail; **verification** of mass times + deceased names only |

**Do NOT** run OpenAI vision on every page of every diocese — that would burn $5 in weeks.

**Do** run a cheap **text correction pass** on extracted blocks: "Mass times", "Parish timetable", "We pray for", "Recently deceased", "Ar dheis Dé", "RIP".

---

## Stronger OCR prompt (vision / Mistral page OCR)

Use this instead of the current `OCR_PROMPT` in `convert_bulletin.py`:

```
You are transcribing one page of an Irish Catholic parish bulletin (English and Irish Gaeilge).

RULES — follow exactly:
1. Output PLAIN TEXT only. No markdown code fences, no ``` blocks, no image references like !img-0.jpeg.
2. Transcribe EVERY word, name, date, and time exactly as printed. Do NOT translate Gaeilge to English.
3. MASS TIMES are life-critical: preserve day names, Vigil/Saturday evening, Holy Day, church names, and times in 12h or 24h form exactly as shown (e.g. "10.30am", "7.30 p.m.", "19:30").
4. DECEASED / PRAYER intentions: every personal name must be letter-perfect — Mc/Mac/O'/Ní/Ní, apostrophes, hyphens, "née", townland names.
5. Multi-column layout: read columns left-to-right, top-to-bottom; separate columns with a blank line.
6. Tables (timetables): one row per line, use " | " between columns.
7. If text is illegible, write [illegible] — NEVER guess a name or time.
8. Ignore decorative headers, page numbers, and repeated diocese mastheads unless they contain parish-specific information.
```

---

## Correction prompt (text-only — run AFTER OCR, on critical sections)

This is the high-value, low-cost step. Send **only** the mass-times and deceased/prayer blocks (not the full bulletin) through `harvester.ai_router.call_ai`:

```
You are a proofreader for Irish Catholic parish bulletins. You receive RAW OCR text from one bulletin section.

Your job: fix OCR errors while preserving meaning. You are NOT allowed to invent information.

SECTION TYPE: {mass_times | deceased_prayers | general}

RULES:
1. Fix obvious OCR mistakes only: l↔1, O↔0, rn↔m, broken apostrophes (O Brien → O'Brien), Mc Mahon → McMahon, St . → St., spurious spaces in times (10 . 30 → 10.30).
2. Irish names: preserve Mc, Mac, O', Ó, Ní, Uí, Ui, hyphenated surnames, and "née" exactly as intended by context. If unsure between two spellings, keep the OCR version and append [?].
3. Mass times: never change a day, church, or time unless the OCR version is clearly garbage (e.g. "l0:30" → "10:30"). List each entry on its own line.
4. Deceased / "We pray for" / "Ar dheis Dé": names are sacred — if any character is uncertain, keep OCR text and mark [?]. Never add or remove a person.
5. Gaeilge: do not translate; only fix obvious OCR corruption (e.g. "6o" → "go" when context is Irish prose).
6. Output the corrected text only — same structure as input, no commentary.

RAW OCR TEXT:
---
{paste section here}
---
```

Optional **JSON verification** pass (still text-only, tiny tokens) for mass times:

```
From this bulletin excerpt, extract mass times only. Return JSON array:
[{"church": str, "day": str, "time": str, "notes": str|null}]
Use exact spelling from the text. If a field is unclear, use null. Return [] if none found. JSON only.
```

---

## Model comparison (Franky's question: what AI is best?)

| Tool | OCR quality | Cost | Verdict |
|------|-------------|------|---------|
| **PyMuPDF text extract** | Perfect on digital PDFs | Free | **Use first always** |
| **Mistral OCR 3** | Very good tables/columns | ~$1–2/1k pages | **Best paid bulk OCR** — already in repo |
| **Gemini 2.5 Flash (vision)** | Good | Free tier limited | Good fallback; upgrade from 1.5-flash |
| **GPT-4o-mini (vision)** | Good | ~$0.15/M tokens | Reserve for hard pages only |
| **Tesseract / PaddleOCR** | Poor on multi-column bulletins | Free | Not recommended for this project |
| **Groq / Mistral chat** | N/A for images | Free | **Perfect for correction pass** |

**Winner for Franky's goals:** Tier 0 free extract + Mistral OCR batch + free text correction. OpenAI $5 = safety net for verification, not primary OCR.

---

## Decisions / standing requests

- [ ] Implement Tier 0 born-digital text extraction in `convert_bulletin.py`
- [ ] Upgrade Mistral model id to `mistral-ocr-2512` (or latest stable)
- [ ] Replace `OCR_PROMPT` and add section-based `CORRECTION_PROMPT` after OCR
- [ ] OCR **per-parish PDFs** where recipes exist (Parish Messenger) instead of only mega-PDF
- [ ] Bump vision fallback to `gemini-2.5-flash` when key available
- [ ] Raise DPI to 200 for image OCR fallback
- [ ] Push to GitHub when Franky says go

---

## Files referenced

- `ocr/convert_bulletin.py` — OCR pipeline + `OCR_PROMPT`
- `ocr/generate_bulletin_pages.py` — HTML layout + entity handling
- `harvester/ai_router.py` — free correction pass routing
- `harvester/events_extractor.py` — post-OCR structured extraction pattern
- `.github/workflows/ocr-bulletin.yml` — diocese mega-PDF OCR trigger
