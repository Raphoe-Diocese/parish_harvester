# What is this?

This repo harvests this week's parish bulletins, stitches a mega PDF for each live diocese, runs OCR on that PDF, and publishes the result to https://www.parishpress.ie/

## The 60-second tour

- **Sunday 09:00 UTC** — GitHub Actions runs the harvest. Frank can also run one parish from the Trainer.
- **Recipes** in `parishes/recipes/` tell the harvester how to find each bulletin PDF.
- **Mega PDF** — one collated PDF per live diocese. This stays on.
- **OCR** — text for the diocese viewer is taken from that mega PDF. Irish stays Irish.
- **Site** — https://www.parishpress.ie/ shows Raphoe, Derry, Clogher, and Down & Connor. Twenty-two other dioceses are stubs.
- **Trainer** — Chrome extension. Install the zip, extract, Load unpacked. Problems tab reads `parishes/parish_status.json` only.

## Where things live

```
parish_harvester/
├── parishes/            recipes + parish_status.json (harvest truth)
├── harvester/           download, stitch, reports
├── ocr/                 mega PDF → viewer HTML
├── docs/                public site source (GitHub Pages)
│   ├── index.html
│   ├── dioceses/        live viewers
│   ├── parishes/        parish pages
│   ├── bulletins/       this-week OCR index (keep index.html)
│   └── mega_pdf/
├── extension/           Parish Trainer source
├── .github/workflows/   harvest.yml, ocr-bulletin.yml, deploy-pages.yml
├── AGENTS.md            product order
├── GAMEPLAN.md          everything else
└── docs/DOMAIN.md       live URLs
```

`/search/`, `/feeds/`, `/badges/`, and `/subscribe/` are not published.

## How a Sunday harvest works

1. `harvest.yml` starts at 09:00 UTC.
2. Each recipe is replayed. Outcome lands in `parishes/parish_status.json`.
3. Parish PDFs are stitched into the diocese mega PDF (`HARVEST_MEGA_PDF=1`).
4. OCR builds the diocese / parish viewer pages.
5. `deploy-pages.yml` publishes `docs/` to https://www.parishpress.ie/

## Trainer

1. Get https://www.parishpress.ie/extension/parish_trainer.zip
2. Extract so `manifest.json` sits at the folder root.
3. `chrome://extensions` → Developer mode → Load unpacked.
4. Train a parish → Send & test. GitHub runs one-parish harvest. Problems refreshes from `parish_status.json`.

Current zip version: **1.61.28**. After a new zip: Reload at `chrome://extensions`.

## What can go wrong

- **Recipe breaks** when a parish site changes. Retrain. Other parishes keep working.
- **Stale bulletin** — the download worked but the file is last week. That row stays on Problems.
- **OCR miss** — text can be incomplete. Trust the original PDF.

Do not run a Full harvest on Frank's 16 GB laptop.

## Help

- Product order: [AGENTS.md](AGENTS.md)
- Website / OCR list: [docs/WEBSITE_OCR_BACKLOG.md](docs/WEBSITE_OCR_BACKLOG.md)
- Other work: [GAMEPLAN.md](GAMEPLAN.md)
- Live URLs: [docs/DOMAIN.md](docs/DOMAIN.md)
- GitHub: https://github.com/Raphoe-Diocese/parish_harvester
