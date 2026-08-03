# Cursor — last result

Last updated: 2026-08-04

## What was completed

- Created project memory/planning files (not committed yet):
  - `PROJECT_PLAN.md`
  - `DECISIONS_LOG.md`
  - `CHECKPOINTS.md`
  - `CURSOR_NEXT_TASK.md`
  - `CURSOR_LAST_RESULT.md`
- Scoreboard helper already on main: `harvester/scoreboard.py` (commit `3faccdf`).
- Post-harvest performance check of Actions run **30750112670** (diagnosed from GitHub API + remote JSON; local clone was still behind).

## Latest full harvest (remote truth)

| Metric | Old baseline | Latest (2026-08-02) |
|--------|--------------|---------------------|
| Downloaded / ok | 44 | 38 |
| Actionable / failed | 63 | 69 |
| Skipped | 16 | 16 |
| Runtime | — | ~5h 21m |

Watchlist from that harvest:

| Parish key | Result |
|------------|--------|
| `ardmoreparish` | PASS |
| `ballymoneyparish` | PASS |
| `stmarysportglenone` | FAIL — recipe outdated |
| `aghagallonandballinderryparish` | FAIL — recipe outdated |

## Current repo state (before sync)

- `git status`: `## main...origin/main [behind 4]`
- Untracked planning/handoff files present (must not be lost on pull).
- Local `Bulletins/report.json` / `parishes/parish_status.json` were **stale** until pull (still showing 2026-07-26 / 44 ok baseline).

## Blockers / open questions

1. Why did Port Glenone fail again as “recipe outdated” after an earlier fix?
2. Why did Aghagallon fail as “recipe outdated” (earlier it looked like stale-but-working after `use_page_url` fix)?
3. Full all-diocese harvest is too slow (~5h+) — diocese split needed.

## Current score

About **7.3/10**.

## Next

See `CURSOR_NEXT_TASK.md`: **sync latest harvest commits**, then stop and report. No commit/push until user approves.
