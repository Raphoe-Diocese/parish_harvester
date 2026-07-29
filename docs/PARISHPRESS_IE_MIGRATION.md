# parishpress.ie — Domain Migration Plan

**Status:** Plan only (domain purchased; DNS/Pages not switched yet)  
**Current live base:** `https://raphoe-diocese.github.io/parish_harvester/`  
**Do not confuse with:** `parishpress.net` (third-party parish bulletin host used by some Raphoe recipes)

## Current architecture

| Layer | Today |
|-------|--------|
| Hosting | GitHub Pages via `deploy-pages.yml` (publishes `docs/` as site root) |
| Org/repo | `Raphoe-Diocese/parish_harvester` |
| Extension updates | `updates.xml` + zip under Pages |
| Collated PDFs | `mega_pdf/*_mega_bulletin.pdf` (path kept for compatibility) |
| OCR archive | `/bulletins/` |
| Diocese pages | `/dioceses/{slug}/` |

## DNS (choose one)

### Option A — apex ALIAS/ANAME (preferred if registrar supports it)
1. `parishpress.ie` ALIAS/ANAME → `raphoe-diocese.github.io`
2. `www.parishpress.ie` CNAME → `raphoe-diocese.github.io`

### Option B — GitHub Pages A records (apex)
| Host | Type | Value |
|------|------|-------|
| `@` | A | `185.199.108.153` |
| `@` | A | `185.199.109.153` |
| `@` | A | `185.199.110.153` |
| `@` | A | `185.199.111.153` |
| `www` | CNAME | `raphoe-diocese.github.io` |

Also add the IPv6 AAAA set from GitHub’s current Pages docs when enabling.

## GitHub Pages configuration

1. Repo → Settings → Pages → Custom domain: `parishpress.ie`
2. Enforce HTTPS (after cert provisions)
3. Commit `docs/CNAME` containing `parishpress.ie`
4. Keep Source = GitHub Actions (already used)

## Code changes (when DNS is ready)

1. Set `PAGES_BASE_URL` in `harvester/manifest_builder.py` to `https://parishpress.ie`
2. Update `docs/PUBLIC_URLS.md`, `SITE_MAP.md`, embed docs, RSS/ICS generators
3. Extension `update_url` / release workflow → `https://parishpress.ie/updates.xml`
4. Add `<link rel="canonical">` on generated pages pointing at parishpress.ie URLs
5. Regenerate sitemap / search-index with new base

Code already corrected away from legacy `frankytyrone.github.io` hardcodes toward `raphoe-diocese.github.io` as the interim canonical.

## Redirects & what breaks

| URL class | Action |
|-----------|--------|
| `raphoe-diocese.github.io/parish_harvester/*` | Keep working (GitHub Pages dual host) OR add notice + canonical |
| Old `frankytyrone.github.io/...` embeds | Broken already for many clients — document migration; optional Pages redirect repo if still owned |
| Parish site iframes pointing at github.io | Update when owners can; keep github.io live during transition |
| `parishpress.net` links | **Leave alone** — different product |

## Recommended public URL structure

```
https://parishpress.ie/
https://parishpress.ie/dioceses/{derry|down-and-connor|raphoe}/
https://parishpress.ie/bulletins/
https://parishpress.ie/bulletins/{diocese}-{YYYY-MM-DD}.html
https://parishpress.ie/bulletins/{diocese}-{YYYY-MM-DD}-ocr.html
https://parishpress.ie/mega_pdf/          # Collated Bulletin PDFs (path stable)
https://parishpress.ie/search/
https://parishpress.ie/extension/
```

Future rename `/mega_pdf/` → `/collated/` only after 301 redirects are in place.

## SEO checklist

- [ ] Custom domain + HTTPS live
- [ ] Canonical tags on home, diocese, bulletin, OCR pages
- [ ] Sitemap URLs use parishpress.ie
- [ ] RSS/ICS `<link>` and item URLs updated
- [ ] Search Console property for parishpress.ie
- [ ] Keep github.io URLs responding 200 during overlap (avoid soft-404 window)

## Rollout order

1. DNS + Pages custom domain + CNAME file  
2. Flip `PAGES_BASE_URL` + docs + extension update URL  
3. Harvest/OCR cycle to regenerate manifests/feeds  
4. Announce embed URL change to parish webmasters  
5. Optional `/collated/` path alias later  
