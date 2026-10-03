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
| Shared bulletin | Clontibret + Muckno; Tyholland + Monaghan & Rackwallace | Harvest once under the host parish. The other parish stays on the A-Z list as a labelled link (`bulletin with …`). Do not pin this week's PDF. |
| `faithful_ie_family_newsletters` | Cork family hubs: OneFaith, West Cork, The Parishioner, OurParish, Bantry `/notices`, Cathedral `/notices/newsletter`, Parishes Together `/notices/newsletters`, Kilbrittain `/bulletin` | Harvest the listing once. Official `/parishes/Name` may 404. `familyofparishes.ie/news` is notices only. Do not pin dated PDFs. |
| Expired HTTPS | Lisnaskea / Galloon | Playwright + `ignore_https_errors` — urllib scrape will fail |
| Ardagh Longford `/pdf/DDMMYY.pdf` | St Mel's — `parishnews.htm` looks yearless/stale; real files are `https://longfordparish.com/pdf/270926.pdf` | `predicted_dated_pdf` (same Tempo pattern). Prove from PDF text dates, not the HTML list. |
| Ardagh Edgeworthstown WP compressed | `edgeworthstownparish.ie/.../parish-newsletter/` — `sunday-newsletter-DD-MM-YYYY-edgeworthstown_compressed.pdf` (+ separate `rathowenstreete_compressed`) | `http_scrape_newest_pdf` with href_patterns. Official directory had no site — kitchen-sink. Streete → alias of Rathowen. |
| Ardagh Mohill WP **pages** | Newsletter is a WP *page* slug `newsletter-27th-september-2026`, not a post. Listing thumbnails lag. Fenagh + Gortletteragh text is inside the Mohill page. | `print_to_pdf` newest Newsletter page (discover via `/wp-json/wp/v2/pages?search=Newsletter&orderby=date`). Alias Fenagh + Gortletteragh → mohill. |
| Ardagh Clonguish / Newtownforbes Docdownloads | Official card had no site. Kitchen-sink: `clonguishparish.ie` same CMS as Drumlish/Aughavas. Newest file `Clonguish Newsletter 27.09.2026#####.pdf` (dated in filename; archive row may show Fri before Sunday). | `http_scrape_newest_pdf` on Docdownloads; score **filename** date. |
| Ardagh Kilronan live twin | Official `kilronanparish.ie` dead. Live: `parishofkilronan.ie/newsletter/` with `/wp-content/uploads/DD.MM.YYYY.pdf`. | `http_scrape_newest_pdf`; score filename. |
| Ardagh Kiltubrid overwritten /news/ | Official card no site. Live `kiltubridparish.com/news/` stacks Sunday HTML (Mass Times & Intentions). | `html_text_bulletin` print_to_pdf + skip_listing_nav. |
| Ardagh Moydow + Legan shared PDF | Official `parishardaghmoydow.com` dead. Live: `ardaghmoydow.com/pdf/DDMMYY.pdf`. Same file covers Ardagh, Moydow, Legan, Ballycloghan. | Harvest under `ardaghandmoydow`; alias `leganballycloghan`. |
| Killala ChurchTV Crossmolina | Current PDF is linked on `churchtv.ie/crossmolina/` but stored under `/wp-content/uploads/2021/02/` while the filename is the real Sunday (`4th-October-…pdf`, proved 04/10/2026). | `http_scrape_newest_pdf` the page. Do not date-rewrite the 2021/02 folder. |
| Killala Mayo.ie newsletters | Belmullet PDF and Ballycroy PNG live on `mayo.ie` parish-newsletter pages. The getmedia GUID changes every week. The date is in the link text and the filename. | Scrape the listing. Do not pin the GUID. PNG is not a PDF/JPEG recipe. |
| `mcn.live` /Camera/ | Webcam page. Weekly PDF is in the church profile JSON (Glenfin and others Frank trained). | `mcn_live_parish_page`. Do not harvest the stream. Do not pin a dated file. |
| `churchmedia.tv` | “View Our Latest Newsletter” on the livestream page (Portaferry). | `churchmedia_newsletter`. Do not pin `/newsletter/<token>`. |
| `churchservices.tv` | Webcam. Sometimes a pointer to a real parish site. | Look for a newsletter on the page. Do not invent a PDF. Do not harvest the stream. |
| `/current-newsletter/` | Same path every week; redirects to this Sunday’s PDF (Naas / Kildare). | `permanent_redirect_document`. Do not pin the dated upload. |

## Clogher leftover after kitchen sink (do not re-hunt blindly)

Facebook / no live weekly file on 22/08/2026: Aughnamullen East, Belleek-Garrison, Brookeboro-Fivemiletown, Cleenish (`parishofcleenish.com` is a COVID ticket page), Clogher town, Eskra, Inniskeen (Kavanagh bulletin **404**), Killeevan, Latton, Pettigo, Rockcorry, Trillick, Tydavnet. Shared (leave skipped): Clontibret → Castleblayney / Muckno; Tyholland → Monaghan & Rackwallace (`past-newsletters`). Killanny `/parish-bulletin` is harvested as stale HTML (May / 2021 lockdown text) until they overwrite it.

## Do not

- Do not harvest Facebook, or invent a PDF because a card says “weekly newsletter.”
- Do not harvest the same shared file twice into the mega PDF.
- Do not harvest Church of Ireland / Anglican twins.
- Do not pin dated filenames, Wix hashes, or `109.228` article ids.
- Do not mark the public diocese page done until harvest writes `docs/dioceses/<key>/`.
- Do not disable `HARVEST_MEGA_PDF`.

## Onboarding pack (one day)

Do **not** start until Frank names the diocese. Kitchen-sink search is the command above. This pack is how that diocese becomes a folder harvest can see.

Killala onboarding started 02/10/2026 (folder `killala`, stem `killala_diocese`, town key `killalaparish`). Official list: https://www.killaladiocese.org/parishes-ministries/parish-details/ (22). Not on the public homepage until a harvest writes `docs/dioceses/killala/`. Do not store `facebook.com/dioceseofkillala` as a parish Facebook. `ballycastleparish.com` is Down and Connor (Antrim), not Mayo Ballycastle.

Today’s live matrix: `clogher`, `cork_and_ross`, `derry`, `down_and_connor`, `raphoe`. **Achonry** onboarding started 27/09/2026 (folder `achonry`, stem `achonry_diocese`) — not live on the public site until first harvest writes `docs/dioceses/achonry/`. Official Achonry cards: https://achonrydiocese.org/parishes/ (23). Joint Achonry+Elphin A–Z: https://achonryelphin.ie/find-your-parish/ — Elphin is a separate diocese letter, do not mix into Achonry evidence. Frank named **Cork** (17/09/2026) — that is **Cork and Ross**, not Cloyne. Harvest `--diocese` uses the **evidence stem**, not the folder name: `achonry_diocese`, `ardagh_diocese`, `armagh_diocese`, `clogher_diocese`, `derry_diocese`, `raphoe_diocese`, `down_and_connor`, `cork_and_ross`.

### 1. Parish list

1. Write the official directory URL (Expand all / parish-details). Keep Irish names. Skip schools. Facebook is a clickable link only.
2. Create `parishes/recipes/<folder>/` — lowercase, underscores, same style as `down_and_connor`.
3. Create the evidence file `parishes/<stem>_bulletin_urls.txt` (copy the Clogher header style). Every parish harvest should see needs a `# --- Name ---` block with `# key:`, `# page:`, then the URL.
4. Create `parishes/<stem>_contacts.json` (or `parishes/down_and_connor_contacts.json` — match today’s four). Each key: `display_name`, `website`, `facebook`.
5. A recipe with no evidence row is invisible (`NO_EVIDENCE_ERROR`). Do not add recipes you did not list.

### 2. Keys and names

- `parish_key` = filename stem, lowercase, no spaces.
- `parish_key` must not equal the folder name (`clogher` parish → `clogherparish`).
- `display_name` is the human name. Keep Gaeilge as Gaeilge.
- Recipe `"diocese"` is the **folder** name (`clogher`), not `clogher_diocese`.

### 3. Wire the diocese (same day, before first harvest)

Add the new stem/folder in **all** of these, copying an existing diocese:

- `parishes/dioceses.json`
- `.github/workflows/harvest.yml` — workflow_dispatch list **and** the S1 matrix
- `harvester/parish_status.py` — `_DIOCESE_LABELS` (stem) and `_RECIPE_FOLDER_DIOCESE` (folder)
- `ocr/generate_bulletin_pages.py` — `CONTACTS_PATH_BY_DIOCESE` (and `_FALLBACK_DIOCESES` only if `dioceses.json` is not enough)

Do **not** add the diocese to `LIVE_DIOCESES` / `OCR_DIOCESE_KEYS` / `EVIDENCE_DIOCESE_KEYS` in `harvester/site_builder.py` until a harvest has written `docs/dioceses/<key>/`. The public page stays a placeholder until then.

`site_patterns.json` — seed a pattern only after a real trick works on this diocese. Copy an existing pattern. Do not invent one.

### 4. First harvest (not on this PC)

```
python main.py --diocese <stem> --dry-run
```

Use GitHub Actions (`workflow_dispatch`, that stem). Do not run a full harvest or download mega PDFs on the 16GB laptop.

`--dry-run` fetches only. It does not move files or stitch the mega PDF.

### 5. Expected `parish_status.json` shape

Each new key must appear under `parishes` with at least:

- `display_name`, `diocese` (the label, e.g. `Clogher Diocese`)
- `category` / `outcome`: `ok` | `stale` | `failed` | `html_only` | `disabled` | `skipped`
- `bulletin_date` as ISO; `bulletin_date_uk` as DD/MM/YYYY
- `actionable` true only when Problems should show the row
- `last_tested_at` set when harvest ran

`summary.total` goes up by the new parish count. `actionable_keys` is the Problems tab.

### 6. Stop / proof

- Stop after this one diocese. Do not start the other 22.
- Proof for S4: folder on `main` with **≥ 10** recipes **and** a green single-diocese harvest run ID written in `GAMEPLAN.md`.

## Proof pack (every new parish)

Source page · found URL · HTTP · file type · date · files changed · tests run.
