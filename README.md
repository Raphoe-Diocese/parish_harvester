# Parish Harvester

Downloads this week's Catholic parish bulletins, stitches one mega PDF per live diocese, then runs OCR on that PDF for the public viewer.

**Site:** https://www.parishpress.ie/  
**Repo:** [Raphoe-Diocese/parish_harvester](https://github.com/Raphoe-Diocese/parish_harvester)

New here? Read [WHAT_IS_THIS.md](WHAT_IS_THIS.md). How agents work: [AGENTS.md](AGENTS.md). Domain URLs: [docs/DOMAIN.md](docs/DOMAIN.md).

## What exists today

- **Four live dioceses:** Raphoe, Derry, Clogher, Down & Connor. Other diocese pages are stubs.
- **Sunday harvest** at 09:00 UTC (`harvest.yml`). Mega PDF stays on.
- **OCR viewer** on each live diocese page (PDF + text). Irish stays Irish.
- **Parish Trainer 1.61.28** — zip, extract, Load unpacked. No auto-update.
- Harvest truth is only `parishes/parish_status.json`.

## Install Parish Trainer

1. Download https://www.parishpress.ie/extension/parish_trainer.zip
2. Extract so `manifest.json` is at the folder root (or run `scripts/refresh_local_trainer.ps1`).
3. Chrome → `chrome://extensions` → Developer mode → Load unpacked → that folder.
4. After a zip change: Reload on that same page.

## Local harvest (one parish)

```bash
python main.py --target-parish bangorparish --diocese all
python -c "from harvester.parish_status import write_parish_status; write_parish_status()"
python -m pytest tests/test_parish_status.py tests/test_patch_report.py -q
```

Do not run a Full harvest or download mega PDFs on a 16 GB laptop.

## Lists (do not start a fourth)

| Work | File |
|------|------|
| Product order | [AGENTS.md](AGENTS.md) |
| Website / OCR pages | [docs/WEBSITE_OCR_BACKLOG.md](docs/WEBSITE_OCR_BACKLOG.md) |
| Everything else | [GAMEPLAN.md](GAMEPLAN.md) |
