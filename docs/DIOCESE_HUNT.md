# COMMAND: Diocese hunt (learning repo)

**This is a command, not a suggestion.** Use it for every new diocese, including the remaining ~24. Do not stop at the official directory’s first handful of PDFs. When a new trick works, write it here and into the Trainer **the same day**.

Clogher 22/08/2026 proved why: Expand-all cards said “no website.” The Parish Websites page + web search + **browser snapshot** (not HTTP scrape) found Magheracloone, Kilmore, Truagh, Clones `.com`, Tempo `/pdf/230826.pdf`, and Ballybay’s live HTML newsletter.

## Command (do not skip a step)

1. **Official directory first** — Expand all / parish-details / new-tab cards. Keep Irish names. Skip school sites. Facebook stays a clickable link (we cannot scrape Facebook). Parish key must not collide with the diocese folder (`clogher` → `clogherparish`).
2. **Second official list** — diocese “Parish Websites” / links page. Scrape real `href`s in a **browser** (markdown fetch strips them). Then **open every href**. Official lists go stale: `aughnamulleneast.com`, `pettigoparish.ie`, `parishofclontibret.com`, `patrickkavanaghcountry.com/html/bulletin.htm` are dead.
3. **Kitchen sink per remaining parish** — web search `"{parish} {alias} parish bulletin newsletter"`. Try `.ie` `.com` `.co.uk`, Irish name, civil name, grouped name (`truagh` vs `errigaltruagh`, `kilmoredrumsnatt` vs Corcaghan). Open Parish Press / churchservices.tv only as a *pointer* to a real site. Ignore Church of Ireland twins (`clogher.anglican.org`, `garrisongroup.org.uk`).
4. **Fingerprint + snapshot + Trainer tools** — do not trust view-source or urllib. Open the page in a browser / Playwright (`channel="chrome"`). Run Trainer **Find bulletin**, **Guess**, **Save guessed link**, fingerprint (`html_fingerprint.js`). If the listing is JS, the live DOM has the Sunday row even when HTTP scrape is blank.
5. **Prove before you claim** — source page, found URL, HTTP 200, file type, **date on the file or page**. Do not invent this Sunday. Stale-but-real (Bundoran Feb 2025, Dromore June 2026) is harvest + stale, not skip.
6. **Remember the trick** — write it into `docs/DIOCESE_HUNT.md`, `extension/html_fingerprint.js`, `extension/site_memory.js` (Back room catalog), `parishes/site_patterns.json`, and the recipe `operator_notes` / `do_not`. Bump Parish Trainer and tell Frank to Reload.

## Trainer / Back room tools (use them)

- **Find bulletin** + HTML fingerprint — CMS plugin / `/pdf/DDMMYY.pdf` / onewebmedia / Wix hash / RTF.
- **Guess** + **Save guessed link** / **Use this link** — writes a real recipe step.
- **Long bulletin** — 8-page weeklies need `max_bulletin_pages` above the default 4.
- **Save page as PDF** — HTML overwritten in place (`skip_listing_nav: true`).
- **site_memory.js** — this is the Back room memory. New playbook goes here so the next diocese sees it.

## Tricks already learned (reuse these)

| Fingerprint / playbook | What it looks like | Recipe |
|---|---|---|
| `http_scrape_newest_pdf` | Dated `.pdf` in listing HTML | Score **filename** not `/uploads/YYYY/MM/` folder |
| `wp_json_newest_media` | WordPress media library | `href_patterns` for bulletin words; harvest UA |
| `predicted_dated_pdf` / `js_dated_pdf_list` | `/pdf/DDMMYY.pdf` (Tempo, Enniskillen, Derry Pattern A) | Listing may be **JavaScript**. HTTP scrape of `news.html` looks empty. Fetch the rewritten PDF. Prefer HTTP if TLS fails. |
| `js_overwritten_html_newsletter` | `parishnews.htm` view-source blank; live page has this Sunday | `print_to_pdf` + `skip_listing_nav` + wait for JS. Do not pin `109.228.27.39/templates/?a=` |
| Wix `/_files/ugd/` hashed PDF | Date is in **link text** only | Click `newest_dated` — never pin the hash (Irvinestown, Truagh) |
| One.com `onewebmedia/*.pdf` | Lisnaskea `23082026.pdf`; Galloon hashed `S25C` + dated text | Click `newest_dated` if cert expired or hash has no date |
| `DD.MM.YYYY` in filename | `Newsletter-23.08.2026.pdf` | Date parser must read 4-digit year **before** `08.20.26` |
| Weekly **RTF** | Magheracloone `23rd-August-2026-.rtf` | HTTP-scrape `.rtf` → LibreOffice to PDF |
| HTML overwritten in place | Culmaine / Donagh / Kilmore parish-news / Tullycorbet | `print_to_pdf` + `skip_listing_nav` |
| Image on Latest Bulletin | Fintona `Sunday-Dth-Month-YYYY.jpg` in an old `/2026/01/` folder | `image_stack` the visible Sunday image. NextGEN `/wp-content/gallery/` is **not** `/uploads/` |
| Dead official hostname | `clonesparish.ie`, `errigaltruparish.com`, `monaghan-rackwallace.ie` | Search the live twin (`.com`, `truaghparish.com`) |
| Shared bulletin | Clontibret + Muckno | Harvest once; other parish is link-only |
| Expired HTTPS | Lisnaskea / Galloon | Playwright + `ignore_https_errors` — urllib scrape will fail |

## Clogher leftover after kitchen sink (do not re-hunt blindly)

Facebook / no live weekly file on 22/08/2026: Aughnamullen East, Belleek-Garrison, Brookeboro-Fivemiletown, Cleenish (`parishofcleenish.com` is a COVID ticket page), Clogher town, Eskra, Inniskeen (Kavanagh bulletin **404**), Killeevan, Latton, Pettigo, Rockcorry, Trillick, Tydavnet, Tyholland. Clontibret shares Muckno — leave skipped. Killanny `/parish-bulletin` is harvested as stale HTML (May / 2021 lockdown text) until they overwrite it.

## Do not

- Do not harvest Facebook, or invent a PDF because a card says “weekly newsletter.”
- Do not harvest the same shared file twice into the mega PDF.
- Do not harvest Church of Ireland / Anglican twins.
- Do not pin dated filenames, Wix hashes, or `109.228` article ids.
- Do not mark the public diocese page done until harvest writes `docs/dioceses/<key>/`.
- Do not disable `HARVEST_MEGA_PDF`.

## Proof pack (every new parish)

Source page · found URL · HTTP · file type · date · files changed · tests run.
