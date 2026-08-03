# Parish Harvester — Project Plan

Last updated: 2026-08-04

## Product goal

Harvest parish bulletins → diocesan mega PDF → OCR → searchable diocesan viewer → public website.

Mega PDF is **core production output**, not optional. OCR and the public diocesan viewer depend on it.

## Current score

About **7.3/10**.

Reason: recent recipe fixes helped a few parishes (Ardmore, Ballymoney), but the latest full harvest went **backwards** overall and took too long.

## Latest full harvest result

Source: GitHub Actions run [30750112670](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/30750112670) (success, scheduled full harvest on `b5fbee5`).

| Metric | Old baseline | Latest (target 2026-08-02) |
|--------|--------------|----------------------------|
| Downloaded / ok | 44 | 38 |
| Actionable / failed | 63 | 69 |
| Skipped | 16 | 16 |
| Runtime | — | about **5h 21m** wall clock |

Recent fix check from that harvest:

- `ardmoreparish` — PASS
- `ballymoneyparish` — PASS
- `stmarysportglenone` — FAIL (recipe outdated)
- `aghagallonandballinderryparish` — FAIL (recipe outdated)

Main time sinks: many parishes burning long timeout budgets (often 250–790s) with concurrency 3 on a full all-diocese run.

## Current priority (do in order)

1. **Sync** latest harvest commits (`git pull` — local was behind origin by 4).
2. **Investigate** why `stmarysportglenone` and `aghagallonandballinderryparish` failed again.
3. **Confirm** `ardmoreparish` and `ballymoneyparish` passed (already true on remote harvest status).
4. **Design** diocese-based harvest split (Raphoe → Derry → Down & Connor).

Do **not** continue mass A–Z recipe repair until 1–3 are done and 4 is at least designed.

## Phase plan

| Phase | Name | Status |
|-------|------|--------|
| 1 | Capture reliability | Largely done; keep guarded |
| 2 | A–Z recipe repair | Paused until post-harvest issues understood |
| 3 | Scoreboard / measurement | Started (`harvester/scoreboard.py`) |
| 4 | Diocese-based harvest split | Next design work |
| 5 | Recipe Brain / Referee | Later |
| 6 | Parish-level OCR pages from mega OCR | Later |
| 7 | Chrome extension / Operator Room | Later |
| 8 | Backend Ready Room | Later |
| 9 | Repo declutter / UI polish | Last |

## Gold standard target

- Per-diocese harvests (not one giant all-diocese wall-clock run)
- Diocesan mega PDFs every production harvest
- OCR from the mega PDF (not separate OCR of every parish PDF by default)
- Parish OCR pages split/reused from mega OCR output
- Recipe Brain / Referee (extension suggests; repo verifies)
- Clean Operator Room (extension UX) after capture/OCR/recipes are reliable
- Clear proof packs before recipe fix commits
- Stable audit packs and scoreboard after every full harvest

## Handoff files

- `CURSOR_NEXT_TASK.md` — exact next agent task
- `CURSOR_LAST_RESULT.md` — last completed result / blockers
- `DECISIONS_LOG.md` — locked decisions
- `CHECKPOINTS.md` — when to measure / refresh audit packs

## Locked rules (short)

See `DECISIONS_LOG.md` for full text. Short list:

- Do not disable mega PDF generation unless explicitly asked.
- Proof pack required before recipe fix commit.
- Extension suggests; repo/referee verifies.
- No UI polish until capture / OCR / recipes are reliable.
- Repo declutter is planned — not before measurement and audit checkpoints.
- Cursor replies: short, copy-paste friendly, one plain code block when asked.
