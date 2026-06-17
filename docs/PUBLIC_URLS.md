# Parish Press — public URLs (Raphoe-Diocese)

**Canonical base:** `https://raphoe-diocese.github.io/parish_harvester/`

> Do **not** add `/docs/` to these paths. The deploy workflow copies `docs/` to the site root.

## Main pages

| Page | URL |
|------|-----|
| Home | https://raphoe-diocese.github.io/parish_harvester/ |
| Derry diocese bulletin | https://raphoe-diocese.github.io/parish_harvester/dioceses/derry/ |
| Down & Connor diocese bulletin | https://raphoe-diocese.github.io/parish_harvester/dioceses/down-and-connor/ |
| Raphoe diocese bulletin | https://raphoe-diocese.github.io/parish_harvester/dioceses/raphoe/ |
| OCR archive (all weeks) | https://raphoe-diocese.github.io/parish_harvester/bulletins/ |
| Search | https://raphoe-diocese.github.io/parish_harvester/search/ |
| Mega PDF tab viewer | https://raphoe-diocese.github.io/parish_harvester/mega_pdf/ |
| Site map | https://raphoe-diocese.github.io/parish_harvester/sitemap.html |

## Extension auto-update (same Pages site)

| Resource | URL |
|----------|-----|
| Extension zip | https://raphoe-diocese.github.io/parish_harvester/extension/parish_trainer.zip |
| Update manifest | https://raphoe-diocese.github.io/parish_harvester/updates.xml |

## One-time setup (if you see GitHub’s 404 page)

1. Open https://github.com/Raphoe-Diocese/parish_harvester/settings/pages
2. Under **Build and deployment**, set **Source** to **GitHub Actions** (not “Deploy from a branch”).
3. Go to **Actions** → **Deploy Parish Press to GitHub Pages** → **Run workflow** → **Run workflow**.
4. When the run finishes green, open the home URL above in a private/incognito window.

If deploy fails with “environment github-pages”, an org admin may need to approve the `github-pages` environment once under **Settings → Environments**.

## When content updates

- Editing files under `docs/` on `main` triggers a new deploy automatically.
- After a harvest (pass or fail), the deploy workflow still publishes `docs/`; mega PDFs are added when the harvest produced them.
