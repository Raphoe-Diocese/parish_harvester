# Cursor — next task

Last updated: 2026-08-04

## Next task

**Sync latest harvest commits** with a clean pull — then stop and report.

Local clone is **behind origin/main by 4** harvest-related commits. Planning files are uncommitted and must not be discarded.

## Exact steps (do these only)

1. Do **not** edit harvest logic, recipes, OCR, or extension code.
2. Do **not** push.
3. Do **not** commit until the user approves.
4. Sync remote harvest commits without losing local planning files, for example:
   - `git status -sb` (confirm behind + untracked planning files)
   - `git stash push -u -m "planning files"` **only if needed**, or keep untracked files as-is and `git pull --ff-only origin main`
   - Prefer: `git pull --ff-only origin main` while untracked `PROJECT_PLAN.md`, `DECISIONS_LOG.md`, `CHECKPOINTS.md`, `CURSOR_NEXT_TASK.md`, `CURSOR_LAST_RESULT.md` remain untracked (safe).
5. After pull, run:
   - `git status -sb`
   - `git log --oneline -5`
   - `python -m harvester.scoreboard`
6. Confirm from **local** `parishes/parish_status.json` / scoreboard:
   - `ardmoreparish` PASS
   - `ballymoneyparish` PASS
   - `stmarysportglenone` FAIL reason
   - `aghagallonandballinderryparish` FAIL reason
7. Update `CURSOR_LAST_RESULT.md` with sync result (still no commit unless user asks).
8. **Stop.** Do not start A–Z repair or harvest-split implementation in the same turn unless the user asks.

## Commits expected from origin (at time of writing)

- `08abc14` chore: add harvested bulletins for 2026-08-02 [skip ci]
- `eb74cd6` chore: clean deployed PDFs [skip ci]
- `3abdbc8` chore: update OCR bulletin viewers for 2026-08-02
- `67c8cff` chore: update parish DNS health snapshot [skip ci]

## After this task succeeds

Next follow-up (separate user prompt):

1. Diagnose `stmarysportglenone` + `aghagallonandballinderryparish` only.
2. Design diocese-based harvest split (no mass A–Z yet).

## Do not do yet

- Mass A–Z recipe repair
- Harvest workflow rewrite
- Extension / Operator Room UI
- OCR pipeline changes
- Repo declutter
- Push / commit without approval
