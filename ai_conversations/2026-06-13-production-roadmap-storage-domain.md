# Production roadmap, storage offload, parishpress.ie domain

**Date:** 2026-06-13  
**User:** Frankytyrone

## Storage — GitHub vs Google Drive / OneDrive

**Already in repo:**
- `harvester/retention.py` + `retention.yml` — zips old PDFs, keeps ~8 weeks individual / 12 weeks mega on GitHub
- `deploy-pages.yml` — deploys PDFs to Pages then **deletes mega PDFs from git** (smart)
- Hard cap warning at 4 GB

**Gap:** Git **history** still grows; cold archive not yet copied to Drive.

**Dead-easy offload (recommended):**
1. After retention zips → `Bulletins/archive/derry-2026-03.zip` etc.
2. GitHub Action uploads zips to **Google Drive** (nonprofit Workspace) via service account — one folder per diocese
3. ParishPress site links: “Live bulletins (GitHub Pages)” + “Historical archive (Google Drive)”
4. **OneDrive** same pattern if preferred (nonprofit M365) — use OneDrive not Outlook email for files

**Outlook email:** good for weekly digest (`email-digest.yml` already stubbed) — not for bulk PDF storage.

## parishpress.net + free .ie domain

- **parishpress.net** = marketing / about / donate
- **bulletins.parishpress.ie** (or similar) → CNAME to `raphoe-diocese.github.io/parish_harvester`
- Add `docs/CNAME` + GitHub Pages custom domain settings
- Main site button: “Read this week’s bulletins →”

## Production checklist (simple)

### Must-have before “production”
1. Push local fixes; CI harvest green 4+ weeks running
2. Retention workflow confirmed (dry run then live)
3. Custom domain on Pages (.ie)
4. Dead-site classifier (DNS-only, keep slow/HTTP)
5. Harvest success >85% on trained parishes
6. OCR: born-digital extract + per-parish events
7. Search fix on bulletin viewer
8. `.ics` calendar subscribe live on subscribe page
9. Cost/storage dashboard monitored
10. Optional: Drive offload for archives >12 months

### Set-and-forget (after training)
- Weekly harvest → OCR → Pages deploy → retention → calendar update (no hands)
- Extension auto-update via `updates.xml`
- Monthly: skim failure report, retrain drifted parishes only

## Maturity score (honest)

| Area | Score |
|------|-------|
| Vision & architecture | 8/10 |
| Automation design | 7/10 |
| **Live reliability today** | **4/10** |
| Public UX | 6/10 |
| Storage planning | 6/10 |
| **Overall production-ready** | **~55% (5.5/10)** |

Not set-and-forget **yet** — 2 dioceses live, harvest CI failing, ~40 parish failures in last report. Right road; ~3–6 months to robust if harvest stabilises.

## User asking right questions?

Yes — storage, domain, production checklist, and “am I on the right road” are exactly the right founder questions.
