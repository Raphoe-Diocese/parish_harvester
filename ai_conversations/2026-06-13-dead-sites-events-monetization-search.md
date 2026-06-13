# Dead sites, events OCR, monetization, search — strategy notes

**Date:** 2026-06-13  
**User:** Frankytyrone

## Dead site detection (keep slow + non-SSL)

**Three buckets only:**

| Bucket | Examples | Action |
|--------|----------|--------|
| **Dead** | DNS NXDOMAIN, connection refused, parked domain, chrome error page | Mark `inactive`, hide from active harvest, keep link with note |
| **Slow** | Loads after long wait, HTTP-only, weak SSL | **Keep** — extend `host_profiles.json` timeout |
| **Broken recipe** | Wrong PDF, outdated selector | **Keep** — retrain, not delete |

**Never** treat harvest timeout alone as dead (cup-of-tea sites).

Already in repo: `status: dead_url` / `inactive` in recipes, manual training prompt in `train.py`.  
**Gap:** no weekly auto-classifier that only marks DNS-dead after 2 consecutive NXDOMAIN checks.

## Events extraction — mega PDF vs per-parish

**Mega PDF in one AI call = why NotebookLM failed here too:**
- `events_extractor.py` caps at **12,000 characters** — most of a diocese mega bulletin is thrown away
- Same OCR blob sent for every parish in `_write_parish_reader_outputs` — wrong context
- AI skips bingo/dances when buried in 28 pages of mass times

**Better approach (per-parish, economical):**
1. Split OCR at parish headings (`PAGE N`, parish name lines)
2. Extract events **per parish chunk** (~2–5k chars) via free `ai_router` (Gemini → Groq → Mistral)
3. Rule-based pre-pass for keywords: bingo, ceili, dance, raffle, coffee morning, fundraiser
4. Validate: must have parseable date; drop hallucinations; never invent on failure

**Cost:** ~1,000 parish chunks/week on free tiers if staggered; paid fallback ~€5–15/month.

**Already wired:** `Bulletins/events/<diocese>/<parish>.json` + `.ics` calendars in `manifest_builder.py`.

## Monetization (community service + “curtains”)

**Free forever (charity mission):**
- Bulletin PDF + searchable text + mass times
- Basic `.ics` calendar subscribe

**Paid optional (diocese sponsorship, not parish punters):**
- Curated “Parish Life” events feed (bingo, dances, fundraisers) with human QA spot-check
- Suggested pilot: **€75–150/month per diocese** or **€500–1,200/year** — one line item for pastoral council
- Do **not** charge individuals early; parishes won't pay €5/month × 1000 parishes

**GitHub nonprofit (Raphoe org):**
- Free Pages hosting + Actions minutes
- **GitHub Sponsors** + Buy Me a Coffee (already on site)
- Auto subscribe without email: **`webcal://` .ics links** (Apple/Google Calendar) — runs itself weekly
- Email list later: Buttondown free tier triggered from GitHub Actions after harvest

## OCR search weakness

**Issues:** search only obvious on OCR tab; diocese landing page uses fragile `innerHTML` highlight; no fuzzy match for OCR typos; entity encoding breaks matches.

**Fixes:** global search bar → auto-switch to text tab; search `textContent`; optional fuzzy (Fuse.js); parish-name jump list.

## Standing backlog

- [ ] Auto dead-site classifier (DNS-only, 2-strike)
- [ ] Per-parish OCR split before events extraction
- [ ] Stronger events prompt (bingo, ceili, social club categories)
- [ ] Search UX fix in viewer template
- [ ] Push when Franky says go
