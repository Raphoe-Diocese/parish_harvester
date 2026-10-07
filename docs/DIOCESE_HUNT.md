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
| `mcn_live_parish_page` leftover skips | Diocese card has no site. `mcn.live/Cameras?County=` still lists a camera. JSON newsletter is beside the camera. | `site_type mcn_live_parish_page`. 03/10/2026: Portarlington, Rathmore, Galway St Joseph this-week PDFs. Do not pin CloudFront UUIDs. Same bytes on two Rathmore cameras = harvest once. |
| Kildare `/current-newsletter/` leftovers | Same Pattern F as Arles/Naas. GET 200 `%PDF` then unskip. | 03/10/2026: Bagenalstown, Borris, Mountmellick were 27/09/2026 weekend files. Abbeyleix still redirected to June 2020 — leave skip. |
| Kildare leftover kitchen-sink twins | Official card often only kandle.ie. Live hosts: kildareparish.ie `/newsletter/`, graiguecullenkilleshin.com homepage PDF, mountrathparish.ie `NewsLetters` (spaces + UUID in filename — score **filename** date, quote the URL), parishnewsletter.killparish.ie HTML posts (PNG on page → print_to_pdf). Monasterevin `/current-newsletter/` redirects to scanner `3341_001.pdf` — date is in the listing link text (`4th October`). | 05/10/2026: Kilcock Pattern F 27th-Sunday `/2026/10/`; Kildare town + alias Nurney/Kildangan; Graiguecullen homepage; Monasterevin Pattern F; Kill HTML; Mountrath + alias Ballyfin. Sallins + Two Mile House alias Naas. Do not pin dated names or scanner/UUID ids. |
| Limerick kitchen-sink | Official card is limerickdiocese.org. Live files: `saintnicholasparish.ie/parish-newsletter/` (04/10/2026 PDF, also St Mary's) and `monaleenparish.ie` wp-json PDF (27/09/2026). | Harvest St Nicholas once. `stmarys` stays skip as bulletin with St Nicholas. |
| Limerick leftover Pattern F | Official card is limerickdiocese.org. Live twin `stjosephsparish.ie/current-newsletter/` redirects to this-week PDF. | `permanent_redirect_document`. 05/10/2026: stjosephs 04/10 PDF 372227 bytes. Do not pin dated name. Do not map Killaloe `sixmilebridgeparish.ie` onto Limerick Cratloe. |
| Kilfenora covered by Galway LIVE | Homepage had a separate coming-soon stub `kilfenora-and-kilmacduagh` while Galway card is already `galway-kilmacduagh-and-kilfenora`. | Remove the duplicate stub from `_CANONICAL_DIOCESES`. Recipes stay in `parishes/recipes/galway/`. Redirect old stub URL to the Galway viewer. |
| Armagh continuous leftover 05/10/2026 | Beragh /pdf/DDMMYY.pdf (041026). Dunleer Pattern F /current-newsletter/. Cullyhanna live twin lowercregganparish.com JPEG Sunday-4th-October-2026-page-001. | predicted_dated_pdf / permanent_redirect_document / http_scrape_newest_images. Do not pin dated names. Official card was Facebook-only for Cullyhanna. |
| Limerick Mura hashed newsletter | Cathedral `Current Newsletter` and Caherdavin listing `Newsletter 270926` use `/index.cfm/_api/render/file/?method=inline&fileID=` hashes. Date is in the PDF or the **link text**, not the UUID. | Click Current Newsletter / scrape newest_dated listing. Do not pin fileID. 05/10/2026: stjohnscathedral 04/10 PDF 2134463 bytes; christtheking 27/09 PDF 860033 bytes. |
| Kilfenora / Kilmacduagh leftovers | Recipes live in `parishes/recipes/galway/` (no separate kilfenora folder). Kinvara JPEG stack is this-week. Ballinderreen is the same file. | Harvest Kinvara once. `ballinderreen` stays skip (`alias_of` kinvara). Clonfertgalway cards, Lisdoonvarna PNG screenshots, Ballyvaughan 20/09 HTML, Ardrahan June 2025 PDFs stay skip. |
| Galway Bearna Duilleog | Official card is clonfertgalway. Live `barnafurboparish.ie/index.php/weekly-duilleog-newsletter/` has dated `4thOct2026.pdf`. Keep Irish (Duilleog, Aifrinn, An Domhnach). | `http_scrape_newest_pdf`. Score filename. Do not pin dated name. |
| Galway Castlegar churchmedia | Official card no file. `churchmedia.tv/st-columba` API newsletter covers Castlegar + Coolough. PDF text `4th Oct 2026`. | `churchmedia_newsletter` slug `st-columba`. Do not pin `/newsletter/<token>`. |
| Galway MCN name collision | `mcn.live/Camera/st-annins-church` is Killannin Rosscahill (no newsletter). `seipeal-n-ainnin-2` is Paróiste an Chnoic / Indreabhán (Tuam-side; not a Galway recipe key). | Do not map Indreabhán’s Nuachtlitir onto `killannin`. |
| Dingle Fógraí | `dingleparish.ie` wp-json media has `October-4th-2026.pdf` plus JPEG previews. HTML Fógraí post is the same week. Keep Irish. | `wp_json_newest_media`, skip jpg. Do not pin the dated PDF. |

| Meath Wix map is not a parish list | https://www.dioceseofmeath.ie/map-of-parishes is Wix CMS (68 parish rows). urllib/SSR showed almost no cards. Second official list: `/priests`. Pastoral areas page has no parish hrefs. | Browser / kitchen-sink the remaining parishes. Do not harvest `facebook.com/dioceseofmeath`. |
| Meath `/current-newsletter/` | Athboy, Dunshaughlin, Kells, Kilbeggan redirect to this-week PDF (same as Kildare). | `permanent_redirect_document` on `/current-newsletter/`. Do not pin the dated file. |
| Meath Squarespace listing with no `.pdf` href | Tullamore `/parish-weekly-bulletin` titles the Sunday file as an article. The PDF is on an inner `/s/` page. Article slug is a hash with no Sunday date, so `post_slug_patterns` cannot score it. | Skip until a listing scrape works. Do not pin `/s/Bulletin-…pdf`. |
| Meath Navan Squarespace dated article + `/s/` PDF | `/bulletin/04-october-2026` carries the Sunday in the slug. Inner `/s/04-October-2026.pdf`. | `http_scrape_newest_pdf` + `post_slug_patterns` `/bulletin/`. Do not pin `/s/`. Not the same as Tullamore hashes. |
| Meath Curraha listing + Ardcath alias | `/bulletin/` has dated Sunday PDF hrefs. PDF title names Ardcath/Clonalvy and Curraha. | `http_scrape_newest_pdf` on `/bulletin/`. Alias `ardcath`. Do not pin dated uploads. |
| Meath Kingscourt WP media iframe | Weekly PDF is in wp-json media / post iframe, not a listing href. | `wp_json_newest_media` with `bulletin` + skip Gyproc. Do not pin `phooriss` dated names. |
| Meath Kilskyre Joomla HTML | `/parish-bulletin/` is this week's notices (no PDF). | `html_text_bulletin` print_to_pdf + `skip_listing_nav`. |
| Meath Clara HTML posts | `/wp/category/newsletter/` newest post is the weekly HTML newsletter. | Click `first_match` then print_to_pdf. Do not pin the dated slug. |
| Meath Beauparc MCN leftover | Parish site newsletters stale. Camera JSON has this-week PDF. Kentstown camera same bytes. | `mcn_live_parish_page` id 629. Harvest once. Do not pin CloudFront UUID. |
| `mcn.live` /Camera/ | Webcam page. Weekly PDF is in the church profile JSON (Glenfin and others Frank trained). | `mcn_live_parish_page`. Do not harvest the stream. Do not pin a dated file. |
| `churchmedia.tv` | “View Our Latest Newsletter” on the livestream page (Portaferry). | `churchmedia_newsletter`. Do not pin `/newsletter/<token>`. |
| `churchservices.tv` | Webcam. Sometimes a pointer to a real parish site. | Look for a newsletter on the page. Do not invent a PDF. Do not harvest the stream. |
| `/current-newsletter/` | Same path every week; redirects to this Sunday’s PDF (Naas / Kildare / Meath). | `permanent_redirect_document`. Do not pin the dated upload. |
| Askea `/newsletters/` dated folder | Holy Family Askea + Bennekerry + Tinryland. Listing HTML has `…/newsletters/YYYY/MM/YYYYMMDD-….pdf`. `/current-newsletter/` is **404**. | `http_scrape_newest_pdf` on `/newsletters/`. Score **filename**. Harvest once under `askea`. Alias Bennekerry + Tinryland. Do not pin `20261004-…pdf`. |
| Kerry diocese card leftovers | Many skips only had the official card. Later weeks upload `Download Newsletter` PDFs under `/wp-content/uploads/2026/10/`. | `http_scrape_newest_pdf` on `dioceseofkerry.ie/parish/<slug>/`. Score filename. 05/10/2026 unskipped 13 (incl. Castlemaine, Abbeydorney, Annascaul, Spa). Do not pin dated names. |
| Kerry Kenmare live twin | Diocese Kenmare card still June 2026. Live listing `kenmareparish.ie/other-information/newsletters/` has `40-Sunday-4th-October-2026-….pdf`. Header names the Kenmare Pastoral Area; the file is Kenmare parish (Holy Cross). Kilgarvan + Tuosist have their own card PDFs. | `http_scrape_newest_pdf` the Kenmare listing. Score filename. Do not harvest that file twice for Glengarriff or Sneem. |
| Kerry St John's wp-json | Diocese St John's card says no newsletter. `stjohns.ie/newsletter/` HTML still linked `2025/07/Newsletter.pdf`. Media library has `041026-newsletter-.pdf` (trailing hyphen; `041026` = 04/10/2026). Keep 9.00am as Gaeilge. | `wp_json_newest_media` on `stjohns.ie`. Do not pin the dated name. Ignore Church of Ireland Ashe Street. |
| Moycullen `/2016/02/` + `DD.MM.YYYY.pdf` | Listing `/newsletter/` has `04.10.2026.pdf` in a stale upload folder. | Score **filename**. Do not date-rewrite `/2016/02/`. Same as ChurchTV `/2021/02/`. |
| Killeigh HTML newsletter | `killeigh.com/newsletter.html` is the weekly bulletin (no PDF). kandle.ie card has no file. | `html_text_bulletin` print_to_pdf + `skip_listing_nav`. Keep Irish. |
| Knocknacarra Wix hash | Homepage hashed `/_files/ugd/` PDF; text `4th October, 2026` / Paróiste Naomh Eoin. | `wix_html` click `newest_dated`. Do not pin the hash. |
| Dublin official A-Z | https://www.dublindiocese.ie/parishes/parishes-a-z/ — 194 territorial `/parish/<slug>/` cards. Website is the table Website cell. Footer Payzone/Crosscare/vocations are not parish sites. | Scrape the card. Do not store facebook.com/dublindiocese. |
| Upload folder is not the Sunday | Balally PDF lives in `/wp-content/uploads/2020/06/` with filename `4th-October-2026-…`. Tuam cathedral PDF lives in `/2026/06/` with filename `Newsletter-October-4th-2026.pdf`. | Score filename date. Do not date-rewrite the folder. Same lesson as Killala ChurchTV `/2021/02/`. |
| Ossory cards 403 | ossory.ie parish pages often hit SiteGround captcha from cloud IP. | Kitchen-sink `{parish}parish.ie` and `{parish}parish.com`. Do not pin dated names. Castlecomer listing titles Twenty sixth Sunday but the PDF filename `Newsletter-2-2.pdf` has no date — leave skip until the file itself is dated. |
| Ossory leftover kitchen-sink 05/10/2026 | Mooncoin Grapevine homepage PDF. Templeorum `/newsletter/` (also `/current-newsletter/` redirect). Ferrybank+Slieverue shared `ferrybankslieverueparishes.ie`. Rosbercon `YYYY.MM.DD.pdf` is the joint Glenmore file from Aug 2026. Ballyhale liturgical `27th-Sunday-in-Ordinary-Time-2026`. Kilmacow `.com` listing 403 — `wp_json_newest_media`. Durrow.ie JPEG `newsletter-04-oct-2026.jpg` in `/2026/09/`. | Scrape the listing. Alias Slieverue → ferrybank, Glenmore → rosbercon. Score filename not folder. |
| Tuam vocations.ie | Many parish-details cards repeat vocations.ie from the diocese footer. | Ignore. Use the real parish host (castlebarparish.ie, tuamparish.com, athenryparish.ie). |
| Shared Dublin / Waterford files | Edenmore + Grange Park same stbenedicts-stmonicas PDF. Narraghmore + Moone same listing. St Paul’s + Butlerstown same stpaulsandbutlerstown.ie PDF (also MCN `st-paul-s` / `buttlerstown` same bytes). Portmarnock + Kinsealy same `/newsletters/` PDF. Saggart + Newcastle same `srbnparishes.ie` PDF. | Harvest once. Alias the other key. |
| Waterford leftover kitchen-sink 05/10/2026 | Clonmel St Mary’s `/newsletter` dated `/images/3rd october 2026.pdf` (link text 4th October). Clonmel SS Peter & Paul `newsletter.php` DDMMYY Web JPEG scans under `/resources/`. Dungarvan monthly `St.-Marys-Parish-Newsletter-October-2026.pdf` — skip Faith-at-Home (not the parish bulletin). Abbeyside newest 13/09. Cappoquin newest July. Sacred Heart `curr_newsletter.pdf` still Sept week. JBM archive ends March. MCN Waterford cameras mostly empty/stale. | Scrape the listing. Alias butlerstown → stpaulswaterford. Do not pin dated names. Do not harvest Faith-at-Home. |
| Tuam mayo.ie leftovers | Official Tuam cards often have no site. Mayo County Council `mayo.ie/en-ie/parish-newsletters/` hosts this-week PDFs for Burrishoole, Kilvine (Ballindine), Ballyhaunis, Balla-Belcarra, Islandeady-Glenisland, Partry-Tourmakeady (27/09). | Same Killala mayo.ie pattern. Scrape the listing. Do not pin getmedia GUID. PNG is not a recipe. Ballintubber/Carnacon/Killawalla same shared file — harvest once (already LIVE). |
| Tuam Corofin `/newsletter.pdf` | Cummer & Kilmoylan live on `corofinbelclare.ie`. Homepage links `/newsletter.pdf` overwritten each week. PDF text carries the Sunday. | `http_scrape_newest_pdf` the homepage. Path is stable undated — not a pin. |
| Tuam Louisburgh `/newsletter/` | Homepage has wide banner JPEGs only. The dated weekly PDF is on `/newsletter/` (`2026-10-04-….pdf`). | Scrape `/newsletter/`. Do not harvest banner JPEGs. Do not pin dated names. |
| Tuam Annaghdown live twin | Official `corrandullachurch.com` DNS dead. Live `annaghdownchurch.com/newsletters/` has `Newsletter-October-4th-2026.pdf`. | `http_scrape_newest_pdf`. Score filename. Keep Irish. |
| Tuam Westport Wix PDF Viewer Pro | `westportparish.ie` post titled 4th October 2026. File is inside PDF Viewer Pro; no scrapeable `.pdf` / ugd href. | Leave skip until a PDF/JPEG href exists (same as Balbriggan). Alias Kilmeena → Westport. |
| Shared Dublin / Waterford files | Edenmore + Grange Park same stbenedicts-stmonicas PDF. Narraghmore + Moone same listing. St Paul’s + Butlerstown same stpaulsandbutlerstown.ie PDF. Portmarnock + Kinsealy same `/newsletters/` PDF. Saggart + Newcastle same `srbnparishes.ie` PDF. | Harvest once. Alias the other key. |
| Dublin leftover kitchen-sink 05/10/2026 | Skip recipes still had a parish host. Later week: `/newsletters/` dated JPEG (Ardlea), `/current-newsletter/` (Blackrock SJB), wp-json `NL2026-MM-DD.pdf` (Terenure), SRBN hub trailing-hyphen `2026-10-Oct-04-News-.pdf`. Firhouse `Weekly-Notice-Partners.pdf` is the amalgam. | Unskip only GET 200 `%PDF`/JPEG + date. Alias shared files. Do not pin dated names. Squarespace `/s/` (Malahide) and Wix `October.pdf` (Balbriggan) stay skip until listing scrape works. |

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
