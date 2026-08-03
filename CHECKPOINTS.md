# Checkpoints

Simple rules for when to stop, measure, and refresh audit materials. If confused: **stop and run a status-only checkpoint**.

---

## After every 3 parish fixes

1. Run a **mini checkpoint** (git status, recent fixes, expected next harvest, next A–Z target).
2. **Refresh the audit pack** (3-file pack on Desktop; stable names below).

## After every major system change

Refresh the audit pack (capture reliability, scoreboard, harvest split, OCR pipeline, etc.).

## Before extension UI / Operator Room work

Refresh the audit pack first. Do not start Operator Room polish on a fuzzy baseline.

## After every full harvest

1. Sync local clone if behind (`git pull`).
2. Run post-harvest scoreboard:

```bash
python -m harvester.scoreboard
```

3. Check recently fixed watchlist parishes.
4. Note downloaded / actionable / skipped vs previous baseline.
5. Note wall-clock duration if available from GitHub Actions.
6. Update `CURSOR_LAST_RESULT.md` with the harvest numbers.

## Proof packs

- Required before recipe fix commits (see DECISIONS_LOG.md).
- Later store under: `parishes/proof_packs/`
- Until that folder is created and used, keep proof evidence in the chat reply / Desktop temp as today — do not invent a new status system in the extension.

## If confused

Stop coding. Run a **status-only** checkpoint:

- `git status -sb`
- `git log --oneline -5`
- `python -m harvester.scoreboard`
- Harvest running? YES / NO / UNKNOWN

Then ask what the one next safe step is. Read `CURSOR_NEXT_TASK.md`.

---

## Stable audit pack filenames

Keep these names stable (Desktop folder `parish_harvester_audit_pack_3files/`):

- `audit_A_core_backend.txt`
- `audit_B_ocr_extension_tests.txt`
- `audit_C_recipes_reports_status.txt`

Do not invent a new 5-file pack naming scheme unless the plan is updated first.

## Current pause (2026-08-04)

Do **not** continue mass A–Z recipe repair until:

1. Latest harvest is synced locally.
2. Port Glenone + Aghagallon post-harvest failures are investigated.
3. Diocese-based harvest split is designed.
