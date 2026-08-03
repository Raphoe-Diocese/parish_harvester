# Decisions log

Decisions that should not be re-argued every session. Add dated entries when something new is locked.

---

## 2026-08-04 — Core product and process locks

### Mega PDF is core production output

Production harvests must produce the collated diocesan mega PDF. OCR and the public diocesan text-bulletin viewer depend on it. Do not disable mega PDF generation unless the user explicitly asks. Single-parish `--target-parish` test runs may skip mega PDF (intentional).

### Harvest batches are diocese-sized first

Harvest work should be sized by **diocese** (Raphoe, Derry, Down & Connor), not random parish batches. Full `all` runs are allowed but are slow; the preferred direction is per-diocese harvest passes.

### Do not OCR every parish separately if mega PDF OCR already exists

Prefer OCR of the diocesan mega PDF. Avoid a default pipeline that OCRs each parish PDF one-by-one when mega OCR already covers the collated bulletin.

### Parish-level OCR pages reuse mega PDF OCR output

When parish OCR pages are built, they should be **split/derived from** the mega PDF OCR output, not from a separate full OCR run per parish unless there is a clear exception.

### Proof pack required before recipe fix commit

For recipe repairs: diagnose → safe fix → proof pack (source page, chosen URL, HTTP/PDF checks, date/stale) → only then commit. No “hope it works” commits.

### Extension suggests; repo/referee verifies

The Chrome extension / Operator Room may propose training and recipes. The repo (and later Recipe Brain / Referee) is the source of truth for what is valid and what harvest accepts.

### No UI polish until capture / OCR / recipes are reliable

Site look, Operator Room polish, and cosmetic work wait until capture reliability, harvest success, and OCR accuracy are in good shape.

### Repo declutter is planned, but not yet

Declutter (junk files, old audit clutter, unused paths) is on the plan. It must not happen before measurement (scoreboard) and audit checkpoints are in place. Parked items in AGENTS.md still apply (e.g. bulletin archive removal when ready).

### Cursor should give short copy-paste replies in one plain code block

When the user asks for a fixed reply format, put the entire answer inside **one** plain code block only. Keep status answers short. Prefer one recommendation unless options are requested. Do not edit/commit/push unless asked.

---

## Related product notes (already in AGENTS.md)

- `parishes/parish_status.json` is the primary “what’s wrong?” file for the Problems tab.
- Dates shown to users: **DD/MM/YYYY**; machine JSON stays ISO.
- Collated Bulletin stitching is core production behaviour.
