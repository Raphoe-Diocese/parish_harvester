# 💷 Cost Dashboard

_Auto-generated at 2026-09-17T08:41:42Z UTC._

_This file is rewritten on every harvest and OCR run. Do not edit manually._

## 🟢 OCR pages this month

_Month 2026-09. Counted from billed Mistral / Gemini / OpenAI pages only. Tesseract is not a bulletin reader and is not counted. Today 4 diocese(s); projection scales that to 26. Mistral ceiling is 2,500 pages from Free **$10** credits at **$4 / 1,000 pages** (mistral.ai/pricing, 15/09/2026). Gemini and OpenAI stay **unknown** unless `OCR_CEILING_GEMINI` / `OCR_CEILING_OPENAI` is set._

| Provider | Pages this month | Free ceiling | % used | At 26 dioceses |
|---|---:|---:|---:|---:|
| Mistral | 0 | 2500 | 0.0% | 0 |
| Gemini | 0 | unknown | unknown | 0 |
| OpenAI | 0 | unknown | unknown | 0 |

Read the three **Pages this month** numbers. Red only if a known ceiling is set and the 26-diocese projection is over it.

## ✅ What's free forever and won't change

- **GitHub Actions** — public repos get unlimited minutes.
- **GitHub Pages** — 100 GB/month bandwidth, no cost.
- **Gemini API** — 1,500 free requests/day (no credit card).
- **Groq API** — 30 free requests/min (no credit card).
- **Mistral free tier** — ~1 request/sec (no credit card).
- **Repository storage** — 5 GB hard cap (zip archives disabled; current-week + mega PDFs stay).

## ⚠️ What could start costing money

| Resource | Free limit | What happens if exceeded |
|---|---|---|
| Repo storage | 5 GB | GitHub warns you; repo may become read-only |
| GitHub Actions (private repos) | 2,000 min/month | Charged per minute |
| Pages bandwidth | 100 GB/month | GitHub may throttle or contact you |
| AI API (if you switch to paid keys) | Varies | Billed to your account |

> **This repo is public** — Actions minutes are unlimited. Storage is the only real risk.

## 🟢 Repository storage

**Used:** 0.012 GB / 5.0 GB hard cap
**Progress:** [░░░░░░░░░░░░░░░░░░░░] 0.2%

Plenty of space. No action needed.

## 🟢 AI API calls

All AI providers used are **free tier**. This section is informational.

- No AI call data recorded yet (Bulletins/ai_router_state.json not found).

**What to do if a provider stops working:** The ai_router automatically falls back to
the next provider (Gemini → Groq → Mistral). Events and summaries will degrade gracefully.

## 🟢 GitHub Actions minutes

Public repositories get **unlimited free minutes**.
_GitHub API not accessible (no GITHUB_TOKEN or GITHUB_REPOSITORY). See https://github.com/settings/billing._

## 🚨 What to do if a 🔴 appears

1. **Storage 🔴**: Do not create zip archives. Tree deletes do not free GitHub quota until a history rewrite (ask first).
2. **Actions minutes 🔴**: Only a risk for private repos. Make the repo public.
3. **AI calls failing**: Check `.env` / GitHub Secrets for your API keys.
   The ai_router falls back automatically — summaries may be missing but harvest continues.


---

_For more detail see [WHAT_IS_THIS.md](../WHAT_IS_THIS.md) — '💷 What this costs Franky' section._
