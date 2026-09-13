# Parish Press domain

**Live site:** https://www.parishpress.ie/

Repo: `Raphoe-Diocese/parish_harvester`. GitHub Pages publishes `docs/` as the site root (`deploy-pages.yml`). The old `github.io` host still works as a dual URL. `parishpress.net` is a different product — leave those parish-site links alone.

## DNS

- `www` CNAME → `raphoe-diocese.github.io`
- Apex A records → GitHub Pages IPs (`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`)
- Settings → Pages custom domain: `www.parishpress.ie`

## Public URLs (this week)

| Page | URL |
|------|-----|
| Home | https://www.parishpress.ie/ |
| Raphoe | https://www.parishpress.ie/dioceses/raphoe/ |
| Derry | https://www.parishpress.ie/dioceses/derry/ |
| Clogher | https://www.parishpress.ie/dioceses/clogher/ |
| Down & Connor | https://www.parishpress.ie/dioceses/down-and-connor/ |
| This-week OCR index | https://www.parishpress.ie/bulletins/ |
| Trainer zip | https://www.parishpress.ie/extension/parish_trainer.zip |

`/search/`, `/calendars/`, `/feeds/`, `/badges/`, `/subscribe/`, and `updates.xml` are **not** published (S3 / C2). Do not add them back.

## Pages source

Settings → Pages → Source = **GitHub Actions**. A `main` push to `docs/` or a harvest/OCR workflow deploys.
