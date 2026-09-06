# GAMEPLAN

The one list for everything that is **not** a website/OCR page job and **not** the
locked harvester product order.

| Where the work lives | Which list |
|---|---|
| Website / OCR / `docs/` pages | [`docs/WEBSITE_OCR_BACKLOG.md`](docs/WEBSITE_OCR_BACKLOG.md) |
| Harvester product order | [`AGENTS.md`](AGENTS.md) locked list |
| Everything else | **this file** |

Rules for this file: write new ideas down the turn they arrive. Do not start
**Parked** work. Do not tick anything **done** without proof Frank can see
(a live URL you opened, a file, or a workflow run ID).

Dates shown to Frank are DD/MM/YYYY. Dates inside JSON stay ISO.

---

## 06/09/2026 — Open PDF looks like last week; harvest missed this week

**The real goal, in one sentence:** this week’s (06/09/2026) bulletins in Open PDF / Download / mega; last week out of the mega; this-week files the harvest skipped picked up.

Harvest **did run** 06/09 (target 2026-09-06, `generated_at` 10:05 UTC). Live megas (HEAD 13:11 GMT) are this week’s files: Raphoe 4,879,457; Derry 6,566,557; Clogher 3,056,825; Down & Connor 5,687,566 at `/mega_pdf/down_and_connor_mega_bulletin.pdf` (underscores). Open PDF and Download are the same URL. Page-1 pictures are this week (Annagry / Aghyaran / Ballybay / Aghagallon). Last week is **inside** later pages.

**Why last week is in the mega:** freshness already treats 30/08 as stale when it can read the date. Ardara `sun-30th-august-26` and Inver `sat_29th__-_sun_30th__august_2026` were **unknown**, so they stayed `ok`. Those sites still only have last week (Ardara news listing; Inver PDF). Bruckless Drive has no URL date.

**This-week files that harvest missed (proved HTTP 200 this turn):** Holy Cross `pdf/060926.pdf`; Loughshore `…/2026/09/23rd-Sunday-in-Ordinary-Time.pdf`; Waterside `…/2026/09/newsletter_060926oo.pdf`. Waterside rewrite had left the file in `/2026/06/`. Loughshore liturgical name was not rewritten. Holy Cross `dated_pdf_path` never ran the HTTP predictor.

**Not a miss (site has no 06/09 file):** Malin (newest April); Ardara; Inver; Saint Malachy’s `bulletin.pdf` still Feb 2025; **Tawnawilly** — newest live PDF is still `Sunday-30th-Aug.pdf` (HTTP 200, 819118 bytes). OCR title is **Sunday 30 August 2026 / 22nd Sunday**. The Mass table lists Sunday 6th Sept as next weekend, so the file looks like this week. Listing text “Sunday 6th Sept” — `Sunday-6th-Sept.pdf` / `Sep` / `September` all 404. Do not invent a 06/09 Tawnawilly bulletin.

**Look-again 06/09 evening:** Fintona latest-bulletin now shows **6 September** (`Sunday-6th-September-2026.jpg` still under `/2026/01/`; `/2026/09/` is 404). Roslea homepage lists `Bulletin-Sunday-6th-Sept-2026.pdf` — predicted `…September-2026.pdf` is 404. Holy Cross / Waterside / Loughshore still 200.

**Merged 06/09/2026 19:14 UTC:** PR [#173](https://github.com/Raphoe-Diocese/parish_harvester/pull/173) squash `f56ed169`. Pages re-deployed the same 06/09 megas (Last-Modified 19:14:32 GMT). Cloud agent **cannot** `workflow_dispatch` harvest.yml (HTTP 403). Frank must tap **▶ Full harvest** in Problems (or Actions → Harvest Parish Bulletins → Run workflow, diocese all, parish empty).

**Phone “23rd August all dioceses” 06/09 evening:** not a stale Open/Download URL. Live page-1 is 06/09. The 23rd is **23rd Sunday of Ordinary Time** (Annagry / Aghyaran / Tullycorbet / Aghagallon). Do not invent a 23/08 mega.

**This turn:** date parse + WordPress folder rewrite + liturgical Sunday rewrite + `dated_pdf_path` / wp-json predicted fallback + Sep/Sept/September filename variants. Recipe fixes not on the live mega until Full harvest.

**Next:** Frank Full harvest. Then Ctrl+F5. Do not tick live until the mega on parishpress.ie drops Ardara/Inver 30/08.

**Parked:** WAF listings (Holywood / St Gerards / St Patricks); timeouts (Port Glenone / Three Patrons); Newtown Killea Cloudflare 403; Ederney 403 in harvest.

---

## 03/09/2026 — Problems console (work-queue polish)

**The real goal, in one sentence:** Frank can see the next parish, the three clicks, and what to do — without harvest jargon on the card.

Locked AGENTS item 2. List still comes from `parishes/parish_status.json` → `actionable_keys`. Extension does not invent parish health.

**Merged 03/09/2026:** PR [#168](https://github.com/Raphoe-Diocese/parish_harvester/pull/168) squash `cda41c98` — tab **Problems**, **Start here**, 3-step how-to, Full harvest in how-to. Trainer **1.61.16**.

**This turn:** each card shows the plain-English advice (`What to do`) already computed by `_problemsFailureAdvice`. Raw harvest error is hover-only when advice exists. Stale dates on that line are **DD/MM/YYYY**. Trainer **1.61.17**. Reload at chrome://extensions.

**Not live on parishpress.ie** — Chrome extension, not the website.

**Next:** Frank Reloads after this PR. Do not start recipe success (item 3) until he says the queue is clear enough.

**Parked:** fewer buttons; recipe success.

---

## 28/08/2026 — Ardstraw East harvested the parishioner form

**The real goal, in one sentence:** stop treating `DataEntryFormPdf.pdf` as this week's bulletin.

Kitchen sink 28/08/2026 (harvest Sunday 23/08/2026): no August file. Newest real Past Newsletter is **Sunday, 5th July 2026** at `http://109.228.27.39/templates/?a=22826&z=19`. `/pdf/` listing 403; predicted dated PDFs 404. Form is 2015. Content gap — harvest that HTML, mark stale. Do not invent 23/08. Do not stamp harvest Sunday on July. Carrick / Lisburn / Tyholland not touched.

**This turn:** recipe clicks only `templates/?a=` newsletter links, `href_skip_patterns` for DataEntry / New Parishioner / GDPR / privacy, `skip_listing_nav`, `disable_stale_rescrape_fallback`. Skip-name + July heading freshness tests. Not harvested this turn. Do not say ok / this week.

---

## 26/08/2026 — Pages must publish committed mega PDFs

**The real goal, in one sentence:** parishpress.ie must serve the smaller files already in `docs/mega_pdf`, not leftover fat harvest artifacts.

PR #139 merged (`f939336b`) and Pages deploy 33021078771 succeeded, but the live mega PDFs stayed 16–18 MB. Two lines in `deploy-pages.yml`: the “latest harvest” download always ran, and Verify copied artifacts first then only copied `docs/mega_pdf` when dest was missing.

**This turn:** skip that harvest-artifact download when committed `*_mega_bulletin.pdf` files exist; always copy `docs/mega_pdf` last (overwrite). Mega PDF stays on. No docs regenerate.

**Live-proved 26/08/2026** after PR [#140](https://github.com/Raphoe-Diocese/parish_harvester/pull/140) squash-merge `a1682ec4` + Pages run [33021470980](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/33021470980) success. HEAD https://www.parishpress.ie/mega_pdf/raphoe_mega_bulletin.pdf is **6,383,586** bytes (`Last-Modified: Wed, 26 Aug 2026 22:57:50 GMT`). Before this deploy it was 17,525,750.

---

## 26/08/2026 — Phone Open PDF + gentle mega compress

**The real goal, in one sentence:** phones can open this week's mega PDF in the same tab, and the four live files are smaller after Pages.

Harvest still builds the mega PDF (`HARVEST_MEGA_PDF=1`). Ghostscript `/ebook` runs after stitch; same page count or the original file is kept. Irish stays Irish. Dates DD/MM/YYYY. No full harvest. No regenerate-all `docs/`.

**Smaller mega bytes are live 26/08/2026** (PR #140 + Pages 33021470980). Raphoe HEAD is 6,383,586. Phone same-tab Open PDF not watched this turn.

**Next:** watch a phone Open PDF staying in the same tab. Do not tick the phone row done until that.

**Parked:** none from this job.

---

## 25/08/2026 — Heading checker: date on the line next to newsletter

**The real goal, in one sentence:** if the masthead date sits on the line
before or after `newsletter` / `bulletin`, treat that as the bulletin date.

Independent audit 25/08/2026: H1 **did run** on Raphoe Drive
(`drive-1jmslbrliw`). Live OCR still prints `Sunday 19 July 2026` then
`RAPHOE PARISH NEWSLETTER` on the **next** line.
`extract_bulletin_date_from_text` only read a date on the **same line** as
the heading, so it returned None and harvest kept `ok`.

**This turn:** same-line heading date still wins first (Holy Cross
`Bulletin 11th & 12th July 2026` → 2026-07-12). If that heading has no
date, look at the previous and next 1–2 **non-empty** lines only when they
are a short date/liturgical line, not a long body paragraph. Do not scan
the whole page. Memorial-only (`died on 9th July 2023`) stays None. H1 and
H3 (ahead-only grace) not reverted. No harvest. No `parish_status.json`
edit. Timeouts not raised. Mega PDF stays on.

**Not live / not harvested.** This does not change parishpress.ie or Raphoe
on the live site until the next harvest. Do not say Raphoe is fixed on
parishpress.

---

## 25/08/2026 — Hunt this-week files for older Problems-tab parishes

**The real goal, in one sentence:** only change a recipe when a **23/08/2026** bulletin is on the live parish site.

Harvest truth is `origin/main` `parishes/parish_status.json` `generated_at` 2026-08-25T13:58:07Z, `target_date` 2026-08-23. No harvest was run. Timeouts not raised. H1/H3/#135 not touched. `parish_status.json` not edited. Carrick / Lisburn / Tyholland not touched. Newtownbutler / Antrim / Loughshore already on main via #137 — this PR does not re-edit those recipes.

| Key | Result | Live proof 25/08/2026 |
|---|---|---|
| **derriaghycatholicparish** | **Fixed** — this-week image is on the listing. Recipe was pinned to 19th Sunday (09/08). Playwright `page.goto` of `?page_id=262` timed out on harvest. | Listing `https://derriaghycatholicparish.com/?page_id=262` HTTP 200. Original `https://derriaghycatholicparish.com/wp-content/uploads/2026/08/21st-Suday-in-ordinary-time.png` HTTP **200** `image/png` 448089 bytes, Last-Modified Mon 24 Aug 2026. Liturgical `21st Sunday in Ordinary Time` → **23/08/2026**. Resized `-724x1024` twin also 200 (519074 bytes). Predicted 20th-Sunday filenames 404. Recipe now `site_type:http_scrape_newest_images` (no browser, timeouts unchanged). Not live / not harvested until the next harvest. |
| **ederney** | **Blocked** — this-week HTML is live; harvest 403 is access, not a missing file. Recipe already `print_to_pdf` + `skip_listing_nav`. No recipe change. | `https://culmaine.co.uk/newsletter` HTTP **200** this turn. Masthead `Sunday 23rd August 2026 21st Sunday in Ordinary Time`. Do not invent a PDF. Do not raise timeouts. |
| **holycrossparishbelfast** | **Content-gap** — filename is this week; **body is still 12/07**. | `http://www.holycrossparishbelfast.com/pdf/230826.pdf` HTTP 200 `application/pdf` 455913 bytes, Last-Modified Fri 21 Aug 2026. Same MD5 as `120726.pdf` (`ac67defb3de0313fa365264355e14f4a`), 13 pages. Do not treat the filename as 23/08. |
| **bangorparish** | **Content-gap** | Listing newest newsletter still `14-June-2026-NEWSLETTER.pdf` HTTP 200 4565986 bytes, Last-Modified Fri 12 Jun 2026. Predicted Aug/Jul NEWSLETTER filenames 404. wp-json newest NEWSLETTER still 14 June (notice docx is not the weekly). |
| **bundoran** | **Content-gap** | Newest real file still `https://magheneparish.ie/wp-content/uploads/2025/02/Parish_Newsletter_09.02.2025.pdf` HTTP 200 1029778 bytes, Last-Modified Sat 08 Feb 2025. Predicted 23/16/09.08.2026 URLs 404. wp-json search `2026` = 0 items. |
| **dromore** | **Content-gap** | NextGEN gallery newest still `…/gallery/bulletin-2026/14th-June.jpg` HTTP 200 `image/jpeg` 753793 bytes, Last-Modified Sun 14 Jun 2026. Predicted Aug/Jul gallery names 404. |
| **dunsfordandardglassparish** | **Content-gap** | Listing headings still top out at `Sunday 5th July 2026`. `SUNDAY-5th-JULY-2026-1.pdf` HTTP 200 `application/pdf` 341138 bytes, Last-Modified Mon 06 Jul 2026. Predicted Aug PDF paths are WordPress HTML, not files. |
| **parishofhannahstown** | **Content-gap** | Wix listing newest still `Bulletin 7th of June` / `Bulletin%207th%20June%202026.docx` HTTP 200, Last-Modified Mon 08 Jun 2026. No August docx in page HTML. |
| **saintanthony** | **Content-gap** | wp-json newest still `Bulletin090826SunOT19afpub.pdf` HTTP 200 587456 bytes (09/08). `Bulletin230826SunOT21afpub.pdf` and `160826` are HTTP **404**. |
| **saintmalachysparish** | **Content-gap** — do not raise the 4-page cap. | Only bulletin link `documents/bulletin.pdf` HTTP 200 2144332 bytes, **6 pages**, Last-Modified Sat 22 Feb 2025. Raising the cap would fake `ok` on that Feb 2025 file. |
| **stoliverplunkettparish** | **Content-gap** | Listing headings end at `28th June 2026`. `Sun-28th-June-26.pdf` HTTP 200 1351887 bytes, Last-Modified Wed 24 Jun 2026. Predicted `Sun-23rd-August-26.pdf` and July/early-Aug names 404. |
| **stpatricksbelfast** | **Content-gap** | Category archive headings newest `Weekly Bulletin for Sunday 5 July 2026`. Sitemap last bulletin loc is `…/weekly-bulletin-for-sunday-5-july-2026/`. Predicted 23/16/9/2 August slugs 404. |
| **stranorlarparish** | **Content-gap** | Archive newest `28th-June-2026.pdf` HTTP 200 192876 bytes, Last-Modified Fri 26 Jun 2026. `/current-newsletter/` 302s to that same file. Predicted July/August filenames 404. |

**Next:** Derriaghy needs a harvest test after merge. Leave the content-gaps stale until the parish posts 23/08. Ederney recipe is already right — harvest 403 is a later access job.

**Parked:** none from this hunt.

---

## 25/08/2026 — This-week recipe hunt (Claudy / Lisnaskea / Newtownbutler / …)

**The real goal, in one sentence:** change a recipe only when a live
23/08/2026 bulletin file is HTTP 200.

Harvest truth is `parishes/parish_status.json` on origin/main
(`generated_at` 2026-08-25T13:58:07Z, target 2026-08-23). No harvest.
No `parish_status.json` edit. H1 / H3 / #135 not reverted. Timeouts not
raised. Limavady / Carrick / Lisburn / Tyholland not touched.

| Key | Result | Live proof 25/08/2026 |
|---|---|---|
| **parishofclaudy** | **Content-gap** — leave `predicted_dated_pdf`. | `NEWSLETTER 23-8-26.docx` (space and `%20`) HTTP **404**. Newest real file `NEWSLETTER 9-8-26.docx` HTTP 200, 25,820 bytes. |
| **lisnaskeamaguiresbridge** | **Already on main** (#135). | Listing `/bulletin.html` HTTP 200. `23082026.pdf` HTTP 200, 596,595 bytes, link text 23rd August 2026. Recipe already `http_scrape_newest_pdf`, no filename pin. |
| **newtownbutler** | **Fixed** — HTTP scrape + link-text date. | Listing `/bulletin-1.html` HTTP 200. Link text **23rd August 2026** → hashed `S25C-*.pdf` HTTP 200, 205,065 bytes. Do not pin the hash. |
| **antrimparish** | **Fixed** — HTTP scrape of `/bulletinpage/`. | `www-static…/2026/08/23rd-August-2026.pdf` HTTP 200, 355,100 bytes, `application/pdf`. Playwright still times out; do not raise timeouts. |
| **malinparish** | **Content-gap**. | `Bulletin-23rd-August-2026.pdf` still HTTP **404**. Newest listing file `Bulletin-5th-April-2026.pdf` HTTP 200, 331,159 bytes. |
| **st-colmcilles** | **Content-gap**. | Listing newest is `Parish-Bulletin-16082026.pdf` HTTP 200, 1,727,015 bytes. Predicted `…23082026.pdf` / `…23rd-August-2026.pdf` are HTML 46,451 bytes (soft 404), not PDFs. |
| **stcolmcillesholywood** | **Content-gap**. | `/bulletin-notice-sunday-23rd-august-2026/` and `Bulletin-Notice-23rd-August-2026.pdf` HTTP **404**. Newest notice still 16th August 2026. |
| **stteresasparish** | **Content-gap** — parish said no bulletin this Sunday. | WP.com post *Please note there is no Bulletin for Sunday, 23rd August 2026*. Newest real bulletin post is 16th August 2026. |
| **loughshoreparishes** | **Fixed** — `wp_json_newest_media`, filter `sunday-in-ordinary-time`. | `21st-Sunday-in-Ordinary-Time.pdf` HTTP 200, 4,513,290 bytes (21st Sunday = 23/08/2026). Do not take `DC-Vocations-Newsletter.pdf`. |
| **parishofmaghera** | **Content-gap**. | `/copy-of-contact-us-2` still only `160826B-0.jpg` / `160826B-1.jpg`. No `230826`. |

**Next:** harvest after merge for the three fixed recipes. Leave the six
content-gaps until the parish posts 23/08.

**Parked:** none from this hunt.

---

## 25/08/2026 — HTTP fetch: IPv4 first + expired-cert fallback

**The real goal, in one sentence:** get Limavady’s already-known
`23-8-26.pdf` without raising recipe timeouts.

Harvest
[32852633310](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32852633310)
(target 23/08/2026, generated 25/08/2026 13:58 UTC): 103 ok, Limavady
**failed** `Total timeout exceeded` with the URL already
`https://www.limavadyparish.org/onewebmedia/23-8-26.pdf`. Proved 25/08/2026:
default `urlopen` → `CERTIFICATE_VERIFY_FAILED` (expired cert);
unverified context → HTTP 200 PDF 685118 bytes. Nine predicted weeks × 12s
IPv6 hang burns the 180s parish cap.

**This turn:** `_fetch_bytes_with_retries` connects IPv4/A-record first, then
retries the same URL once unverified only after a cert-verify/expired error.
404/410 stay a hard miss. No `timeout_ms` / `total_timeout_s` /
`per_attempt_timeout_s` / `total_budget_s` raised. Limavady stays
`predicted_dated_pdf` (example still `23-8-26.pdf`). Claudy not changed.
Lisnaskea switched to `http_scrape_newest_pdf` now the helper ignores expired
certs. H1 and H3 not reverted. No harvest. No `parish_status.json` edit.

---

## 25/08/2026 — H1 safety-net hole (undated URL still `ok`)

**The real goal, in one sentence:** old Drive / hashed / `bulletin.pdf` files
must not stay `ok` when the PDF heading is last month.

H1 (`freshness_after_unknown_url`, PR
[#129](https://github.com/Raphoe-Diocese/parish_harvester/pull/129)) already
runs in `_recover_stale_bulletin`. The second-pass gate
`apply_freshness_safety_net` was still URL-only, so `unknown` slipped through
when recover was skipped or results were rebuilt from cache.

**Proved still `ok` on GitHub status 25/08/2026** (live OCR body, title
23/08/2026): Raphoe `drive-1jmslbrliw` **Sunday 19 July 2026**; Banagher
**28th June 2026**; Melmount **12 July 2026**; Ardstraw East **5th July 2026**.

**This turn:** safety net now runs the same H1 heading check when the URL
verdict is `unknown` and a PDF is on `result.file_path`. Mark stale only when
the heading is provably old. This-week heading stays not-stale. Memorial-only
/ no bulletin heading stays unknown. H1 and H3 not reverted. No harvest. No
`parish_status.json` edit. Not live until the next harvest.

---

## 24/08/2026 — Limavady recipe pin (this week’s file)

**The real goal, in one sentence:** stop harvest using a stale Limavady example
URL so the first guess is this week’s `23-8-26.pdf`.

Frank proved on 24/08/2026 (screenshots win): listing
https://www.limavadyparish.org/parish%20bulletins.html first button
**23rd August 2026**; opened PDF `23-8-26.pdf` header **23 August 2026**,
**TWENTY-FIRST SUNDAY IN ORDINARY TIME**. Harvest `parish_status.json` on
main still says `ok` with `16-8-26.pdf` (last_tested 23/08/2026 22:36 UTC) —
that file was **not** edited this turn; do not invent ok/stale.

Cause: `predicted_dated_pdf` replay uses the **step** URL first. The step was
still pinned to `28-6-26.pdf`; `weeks_back` then finds last week
`16-8-26.pdf`. Pattern B rewrite already maps to `23-8-26.pdf` for Sunday
23/08/2026 (existing
`test_padded_dd_mm_yy_rewrite_keeps_zeros`). Sunday harvest almost certainly
404’d this week’s file (not uploaded yet) and kept last week. Old H3 grace
then called that `ok`. **Stale example URL in the recipe, not a rewrite bug.**

**This turn:** `parishes/recipes/derry/limavadyparish.json` now points
`start_url` and `steps[0].url` at `23-8-26.pdf`. Kept
`site_type: predicted_dated_pdf`, `weeks_back: 8`, timeouts, and `do_not`
(still no `use_captured_url`). `recorded_date` `2026-08-24`. Next Sunday
rewrite must become `30-8-26.pdf`. **H3 already merged** as PR
[#131](https://github.com/Raphoe-Diocese/parish_harvester/pull/131)
(`42861123` / `8eef477c`) — **not reverted**. No other recipes touched. No
harvest. No `parish_status.json` edit. Not live / not harvested until the
next harvest — do not tick this done as live. Merged as PR
[#132](https://github.com/Raphoe-Diocese/parish_harvester/pull/132).

## 24/08/2026 — Problems-tab recipes (Malin / Bangor / Malachy / Kilmore / Anthony / Derriaghy)

**The real goal, in one sentence:** only fix a recipe when a **23/08/2026** bulletin URL is on the live parish site.

Harvest truth is `parishes/parish_status.json` on `origin/main` (`last_tested_at` 2026-08-23T22:36:52+00:00). No harvest was run. H3 (PR #131) was not touched. Limavady was left for the other agent (PR #132 already on main). Carrick / Lisburn / Tyholland not touched.

| Key | Result | Live proof 24/08/2026 |
|---|---|---|
| **kilmoreandkillyleagh** | **Fixed** — recipe was pinned to `9th_august_2026__1_.pdf`. Listing now has this week's file. | Listing `https://www.kilmoreandkillyleagh.com/latest-notices--downloads.html` (HTTP 200). File `https://www.kilmoreandkillyleagh.com/uploads/8/7/4/5/8745725/23rd_august_2026_combined-1.pdf` HTTP **200**, 2,151,572 bytes, `Last-Modified: Sun, 23 Aug 2026 18:16:42 GMT`. URL date 23/08/2026. PDF heading `23rd August 2026` / `21st Sunday of Ordinary Time`. **7 pages** (weekly bulletin + Mass readings, not a magazine) → `max_bulletin_pages=10`, `site_type:http_scrape_newest_pdf`. |
| **malinparish** | **Content-gap** — do not invent. | Listing `https://malinparish.ie/index.php/bulletin/` HTTP 200. Newest listing/wp-json file is still `Bulletin-5th-April-2026.pdf` (HTTP 200, 331,159 bytes). Status URL `…/2026/08/Bulletin-23rd-August-2026.pdf` is HTTP **404** (predicted rewrite; file is not on the site). |
| **bangorparish** | **Content-gap** — do not raise the 4-page cap. | Listing `https://www.bangorparish.com/parish-bulletin/` HTTP 200. Newest newsletter still `14-June-2026-NEWSLETTER.pdf` (HTTP 200, 4,565,986 bytes, **4 pages**, heading `14th June 2026`). Predicted 23/16/09 Aug NEWSLETTER filenames 404. `bangor-parish-200823.pdf` is 2023 (`Last-Modified: Mon, 21 Aug 2023`). Harvest's "6 pages" is not this week's weekly. |
| **saintmalachysparish** | **Content-gap** — do not raise the cap. | Homepage `https://www.saintmalachysparish.com/` HTTP 200. Only bulletin file `https://www.saintmalachysparish.com/documents/bulletin.pdf` HTTP 200, `Last-Modified: Sat, 22 Feb 2025`, **6 pages**, heading `Sunday 23rd February 2025`. Raising `max_bulletin_pages` would fake `ok` on that Feb 2025 file. |
| **saintanthony** | **Content-gap** — do not invent. | Listing `https://saintanthonys.uk/parish-bulletin/` HTTP 200 (no PDF href). wp-json newest bulletin still `Bulletin090826SunOT19afpub.pdf` (HTTP 200, 09/08/2026). `Bulletin230826SunOT21afpub.pdf` and `Bulletin160826SunOT20afpub.pdf` are HTTP **404**. |
| **derriaghycatholicparish** | **Content-gap** — do not invent. | Homepage + `?page_id=262` HTTP 200 (slow One.com, but HTTP scrape worked). Newest dated bulletin image still `19th-Suday-in-ordinary-time-724x1024.png` (HTTP 200, `Last-Modified: Fri, 07 Aug 2026` = 19th Sunday OT = 09/08/2026). Predicted 20th/21st Sunday filenames 404. |

**Next:** leave the five content-gaps stale/failed until the parish posts 23/08. Kilmore needs a harvest test after merge.

**Parked:** none from this hunt.

---

## 23/08/2026 — Brittleness audit (what can lie to us)

**The real goal, in one sentence:** find the places where harvest says `ok` but a
reader gets the wrong week, an error page, or nothing — and the places where one
small failure hides a big one.

Audit only. Nothing was implemented, no recipe was touched, no harvest was run,
no PDF was downloaded. Everything below was read on a fresh clone of
`origin/main` at commit `48280c42`, and the live checks were run 23/08/2026.
This does **not** redo the archive/this-week audit in the section below it.

### The one thing to fix first

**`ok` does not mean the reader gets this week's bulletin.** Three live pages
prove it, all titled `23/08/2026`, all `outcome: ok` in
`parishes/parish_status.json`:

| Live page (checked 23/08/2026) | What it actually shows |
|---|---|
| [`/parishes/clogher/killanny-ocr.html`](https://www.parishpress.ie/parishes/clogher/killanny-ocr.html) | May **2021** — `Ascension of The Lord`, `Pentecost Sunday`, `16th May`. HTTP 200, `Last-Modified: Sun, 23 Aug 2026 22:47:57 GMT` |
| [`/parishes/raphoe/drive-1jmslbrliw-ocr.html`](https://www.parishpress.ie/parishes/raphoe/drive-1jmslbrliw-ocr.html) | Raphoe parish, body header `Sunday 19 July 2026 RAPHOE PARISH NEWSLETTER`. HTTP 200, `Last-Modified: Sun, 23 Aug 2026 23:16:54 GMT` |
| [`/parishes/down_and_connor/sacredheartparishbelfast-ocr.html`](https://www.parishpress.ie/parishes/down_and_connor/sacredheartparishbelfast-ocr.html) | An Apache **503 Service Unavailable** page — `The server is temporarily unable to service your request due to maintenance downtime` |

Readers are being shown Mass times for the wrong week. That is the worst
failure this product can have.

**Why, in code (two gaps, not one):**

1. `harvester/bulletin_freshness.py` `check_bulletin_freshness` returns
   `unknown` when the URL carries no date (line 324, `no_date_in_url`), and
   `harvester/fetcher.py` `_recover_stale_bulletin` line 1972 only rejects
   `verdict.status == "stale"`. So `unknown` is accepted as this week.
   Measured on `origin/main` for target 2026-08-23: of the **112** `ok` rows,
   **64** were genuinely date-checked (`in_bulletin_week`), **39 (35%) came back
   `unknown:no_date_in_url`** — nothing checked the week at all — 8 passed only
   on the grace window, 1 on `upload_folder_matches_target_month`.
2. **No body-date check runs on the normal path.**
   `harvester/fetcher.py` `extract_pdf_bulletin_date` (line 447) is only called
   from `classify_page_capped_pdf` (line 492), which only runs when a PDF
   *exceeds* the page cap. That is why Holy Cross Belfast (13 pages) was caught
   as `stale` and Raphoe parish (short PDF, July body) was not.

`harvester/html_capture.py` `pick_best_link` line 194 makes it worse for HTML
parishes: it accepts a link when `best_score[2]` is set, and `best_score[2]`
(`not_stale`, line 172) is **1 for an undated link**. So on a listing page with
no this-week link, an undated link is followed and printed as this week's
bulletin.

**H1 — small harden.** In `_recover_stale_bulletin`, when the URL verdict is
`unknown` *and* a PDF was produced, read the body date with the existing
`extract_pdf_bulletin_date` and judge it with the existing
`verdict_for_extracted_date`. Both helpers already exist and are already
tested; nothing new is invented. `extract_bulletin_date_from_text`
(`bulletin_freshness.py` line 261) only reads dates off `bulletin` /
`newsletter` / `parish news` heading lines, so it will not trip over a
`© 2012-2026` footer and it does not touch Irish text. ~1 file, ~15 lines,
1 test. Parishes whose PDF has no heading date stay `unknown` → unchanged; only
**provably** old bodies flip to `stale`.
**H1 status 24/08/2026: tests proved, not live.** PR
[#129](https://github.com/Raphoe-Diocese/parish_harvester/pull/129)
(`e39b961e`). Targeted
`python -m pytest tests/test_bulletin_freshness.py tests/test_fetcher_capture_reliability.py -q`
= 44 passed. Undated URL + July heading → `stale`; no heading / this-week
heading stay `unknown`. This does **not** change parishpress.ie until the
next harvest — do not tick H1 done as live/harvested. H2 tests proved. H3 tests proved, not live.

### Also NOW — two more one-file hardens

**H2. The junk-page guard has no 5xx phrases.**
`harvester/report.py` `_ERROR_PAGE_PATTERN` lines 26–30 matches captcha /
403 / 404 / access-denied wording only. `docs/parishes/down_and_connor/sacredheartparishbelfast.pdf`
(19,231 bytes) is a captured Apache 503 page, it passed the guard, it is
`ok`, and it is live (above). Add `503` / `502` / `500` /
`service unavailable` / `bad gateway` / `gateway time-out` /
`internal server error` / `under maintenance` / `temporarily unavailable` to
that same deliberately-narrow regex. 1 file, 1 regex, 1 test. The existing rule
still holds: it must never fire on "no extractable text", because `image_stack`
photo bulletins legitimately have no text layer.
**H2 status 24/08/2026: tests proved, not live.** PR
[#130](https://github.com/Raphoe-Diocese/parish_harvester/pull/130)
(`389ac77f`). Targeted
`python -m pytest tests/test_report_error_pages.py -q` = 10 passed. Apache
`503 Service Unavailable` / `temporarily unable to service your request`,
`502 Bad Gateway`, and `500 Internal Server Error` flagged; `Collection €500`
and the existing real-bulletin / blank image_stack / unreadable-file cases
not flagged. Same deliberately-narrow regex — no bare `500`. This does
**not** change parishpress.ie until the next harvest — do not tick H2 done
as live/harvested. H3 tests proved, not live. `harvester/stitcher.py` still has the old
copy of the regex — parked, not edited.

**H3. The 8-day grace window accepts last Sunday as this Sunday.**
`harvester/bulletin_freshness.py` line 289 —
`abs(days_from_target) <= MAX_STALE_DAYS_FROM_TARGET` with the constant at 8
(line 30). `week_window` (line 71) is already the correct Sunday−6…Sunday, so
the whole negative half of the grace window is the bug. This week **8** `ok`
parishes sit at exactly **−7 days** — last Sunday's file:
`limavadyparish` (`16-8-26.pdf`), `st-colmcilles`
(`Parish-Bulletin-16082026.pdf`), `stcolmcillesholywood`, `stgerardsparish`
(`sunday-bulletin-16th-august-2026`), `stteresasparish`
(`…for-sunday-16th-august…`), `stmarysportglenone` and `loughshoreparishes`
(`20th-Sunday-in-Ordinary-Time`, which was 16/08/2026), `parishofmaghera`.
Live proof: [`/parishes/down_and_connor/st-colmcilles-ocr.html`](https://www.parishpress.ie/parishes/down_and_connor/st-colmcilles-ocr.html)
is titled `St Colmcilles Text Bulletin — 23/08/2026` and contains `16 August`.
Harden: make the window one-sided — keep the *ahead* tolerance (parishes really
do post Thursday/Friday for next Sunday; see `_HTTP_SCRAPE_AHEAD_DAYS = 7` in
`harvester/replay.py` line 1573) and drop the *behind* tolerance back to the
bulletin week. ~3 lines.
*The file already admits this:* the comments at lines 45–53 and 124–132 say
antrimparish and st-colmcilles "only passed by accident, via the 8-day grace
window", not on a correct `in_bulletin_week` match.
**Say this out loud before doing it:** 8 parishes flip `ok` → `stale`, the
Problems tab jumps from 15 to about 23, and the homepage ready counts drop.
That is the truth, not a regression — but it must not be a surprise.
**H3 status 24/08/2026: tests proved, not live.** PR
[#131](https://github.com/Raphoe-Diocese/parish_harvester/pull/131)
(`8eef477c`). Targeted
`python -m pytest tests/test_bulletin_freshness.py tests/test_fetcher_capture_reliability.py -q`
= 45 passed. Last Sunday (Aug 9 vs 16 Aug) is `stale` / `date_behind_of_target`;
Thursday 20/08 vs 16/08 is `fresh` / `within_grace_days`; +9 days is
`date_ahead_of_target`. `week_window` unchanged. This does **not** change
parishpress.ie or `parish_status.json` until the next harvest — do not tick
H3 done as live/harvested. About 8 parishes will flip `ok` → `stale` on that
harvest; Problems will get longer; homepage counts will drop. That is
intended. Do not list those 8 as already stale. H4 not started.

### NEXT — after the three above land

- **H4. `last_tested_at` lies for 158 of 161 parishes.**
  `harvester/parish_status.py` line 223 falls back to
  `report.get("last_patched_at")` for any row with no per-row stamp, and
  `harvester/report.py` line 446 sets `last_patched_at` on *every*
  single-parish patch. Proof on `origin/main`: only **4** report rows carry
  their own `last_tested_at` (`kincasslagh`, `clones`,
  `parishofballinascreen`, `castleblayney`) yet **158** parish_status rows all
  read `2026-08-23T22:36:52+00:00` — Castleblayney's test time. The extension
  shows that date in Problems/Directory, and
  `extension/github_recipe_push.js` lines 591–596 uses "did `last_tested_at`
  change?" to decide a Send & test finished, so two overlapping tests can make
  one parish report the other's result. Harden: drop the fallback (leave
  `null`) or add a separate `status_generated_at`. 1–2 files + tests.
- **H5. Pattern F invents URLs that never existed.**
  `harvester/utils.py` `rewrite_date_url` lines 1064–1073: when no date pattern
  matched the *filename*, it still rewrites any `/YYYY/MM/` within ±1 year of
  target. That is how Bundoran got recorded as
  `http://magheneparish.ie/wp-content/uploads/2026/08/Parish_Newsletter_09.02.2025.pdf`
  — an August-2026 folder with a February-2025 filename, HTTP 404 (already
  proved in `docs/WEBSITE_OCR_BACKLOG.md`). Related: `_D_M_YYYY_DOT_RE`
  (`Newsletter-23.08.2026.pdf`, `utils.py` line 41) can be *read* by
  `extract_date_from_string` but has **no rewrite branch**, so Kilmore-shaped
  filenames fall through to the same blanket folder rewrite. Harden: skip the
  Pattern-F folder-only rewrite when `extract_date_from_string(basename)` finds
  a date — a dated filename we cannot rewrite should stay untouched, not be
  half-rewritten into a 404. The Iskaheen `1.jpg` case the branch was written
  for is unaffected (undated filename).
- **H6. `# DISABLED` disables nothing in the fetcher.** `harvester/fetcher.py`
  contains **zero** references to `DISABLED`; only
  `harvester/parish_status.py` `_parse_disabled_keys` (line 47) reads it, and
  that only changes the *display*. Coleraine (St John), Greencastle and Long
  Tower all keep a live URL line under their `# DISABLED` comment
  (`parishes/derry_diocese_bulletin_urls.txt` lines 264–268, 287–294,
  304–312) and are fetched every single week. Live 23/08/2026:
  `https://greencastleparish.com/` 302s to
  `http://ww80.greencastleparish.com/?subid1=bf7ad5ab-…` → HTTP **502** (the
  parked/affiliate redirect the evidence file flagged on 2026-08-10), and the
  generated page `docs/dioceses/derry/index.html` publishes
  `<a class="parish-link" href="https://greencastleparish.com/" target="_blank" …>Greencastle</a>`.
  Two small hardens: (a) make `parse_evidence_file` skip a `# DISABLED` block;
  (b) in `ocr/generate_bulletin_pages.py` `render_parish_link_grid` line 805,
  do not fall back to an external href for a key whose parish_status outcome is
  `disabled`. Overlaps the 23/08 "useful reader link only if already proved"
  backlog row — that one covered `harvester/diocese_intro.py`; this is the
  A–Z grid, a different generator.
- **No same-origin check after a redirect.** `harvester/fetcher.py`
  `_try_force_html_to_pdf` line 857 returns `url=page.url or url`, and the only
  acceptance test is "PDF ≥ 4096 bytes" (`HTML_RENDER_MIN_BYTES`, line 105).
  An expired parish domain that gets parked can therefore be captured and
  reported `ok` under the squatter's URL. Small harden: reject when the final
  registrable domain differs from the one we asked for.
- **H7. `ok` also does not mean the slice made it into the mega PDF.** 12 of
  113 published parish PDFs are ~1.7 KB placeholders reading *"PDF slice
  unavailable — This parish is marked OK, but its page range could not be found
  in this week's mega OCR"* (`annagryparish`, `stteresasparish`,
  `parishofmaghera`, `clontibret`, `tyholland`, `iskaheenparish`,
  `stgerardsparish`, `saintanthony`, `fintona`, `kilmoreandkillyleagh`,
  `ourladyqueenofpeacekilwee`, `newtownbutler`). The placeholder text is
  honest; the `ok` and the homepage ready count are not. Harden: surface a
  `slice_missing` flag rather than redefining `ok` — do **not** touch the mega
  PDF for this.
- **H8. Two URL encoders, only one of them hardened.** The Clones fix,
  `harvester/utils.py` `quote_http_url` (line 375), is used at just **3** call
  sites, all in `harvester/replay.py` (981, 1707, 1855). `harvester/fetcher.py`
  still hand-rolls `.replace(" ", "%20")` at 833, 1177, 1310, 1818, 2032, 2270
  and 2327, plus `harvester/pattern_detector.py` line 135. `.replace()` misses
  non-ASCII (Irish fadas in a filename), `[`/`]` and quotes; **neither** helper
  handles a raw space in the *query string* or a literal `#` (urlparse turns it
  into a fragment and the server never sees it). Harden: route every site
  through `quote_http_url` and extend it to the query, so the next
  Clones-class URL does not need a per-parish fix.

### CI — one new item, and a note on N3

- **H9. `--maxfail=5` in `pytest.ini` (line 16) hides the suite.** Reproduced
  in this audit: with one dependency missing, `python -m pytest --collect-only`
  reported `99 tests collected, 5 errors` and stopped. With the dependency
  installed the real suite is **562 passed, 1 skipped, 1 xfailed** in 84s. That
  is the same mechanism as the harvest gate's `collected 1 item / 5 errors`, so
  **even after N3 lands**, one bad import will still truncate CI into looking
  nearly green. Harden: drop `--maxfail=5` from `pytest.ini` and keep it as a
  local flag. 1 file, 1 line.
- **Note on N3 (do not duplicate it):** the existing N3 fix stands. Worth
  knowing that adding `pythonpath = .` to `pytest.ini` fixes bare `pytest`
  as well, so it also works for anyone typing `pytest` locally. Same one-line
  spirit — N3's owner can take it or leave it.
- **H10. A silent skip is hiding an open bug.**
  `tests/test_sparse_page_ocr.py` line 161 skips unless
  `docs/parishes/raphoe/annagryparish.pdf` is at least 20,000 bytes. That file
  *is* committed — as a **1,713-byte** "PDF slice unavailable" placeholder — so
  the one test that would catch the open "Annagry image OCR smashed" backlog
  item never runs, in CI or locally. Harden: point it at a small committed
  fixture, or mark it `xfail` so it is visible instead of invisible.

### OCR / generator

- **H11. Diocese viewer HTML is written non-atomically.**
  `ocr/parish_pages.py` line 61 has a hardened `_write_text` (strips NULs,
  atomic replace, 3 retries). `ocr/generate_bulletin_pages.py` writes the
  diocese viewer trio with plain `path.write_text` at lines 2421, 2426, 2431,
  2458, 2463, 2468 and 2534 — the exact files GitHub Pages serves for a whole
  diocese. Already named on the 2026-08-23 "Faithful searchable OCR" backlog
  row ("Windows NUL/lock writes skipped dioceses") and still not fixed here.
  Harden: reuse the same helper. I did **not** reproduce a crash; the concrete
  defect is that the hardened writer exists two files over and is not used.
- Everything else on the OCR list (`_ORDINAL_DUP_RE` eating `22nd`, banner
  swallow, `_is_url_only_line`, Annagry columns) is already owned by the
  2026-08-23 backlog row. Not re-listed here.

### Checked and genuinely fine — do not "fix" these

- `harvest.yml` line 126 keeps `HARVEST_MEGA_PDF: "1"`. Locked, correct.
- The report commit step (`harvest.yml` line 399) has **no**
  `continue-on-error`. Correct.
- `main.py` lines 372–381 make a parish_status write failure loud **and**
  fatal (`::error::` then `raise`). Exactly right.
- Dispatch 403 is already handled with a real message —
  `extension/github_recipe_push.js` line 281, *"PAT missing 'workflow' scope"*.
- The extension does not invent parish health: Problems reads
  `actionable_keys` straight from parish_status
  (`extension/sidepanel.js` lines 1388 and 2521).
- The hide-chrome `child.contains(root)` guard from the AGENTS.md gotcha list
  is correct in **both** copies — `harvester/html_capture.py` lines 120 and 263.
  No blank-1KB regression there.
- `_is_real_pdf` (`harvester/fetcher.py` line 404) now folds in the page-count
  check for every caller. Good.

### I don't know — keep, do not act on these yet

- **Two evidence-file parsers that can drift.** `harvester/fetcher.py`
  `_HEADER_DASH_CLASS` (line 107) accepts `-`, `–` and `—`;
  `harvester/parish_status.py` `_HEADER_RE` (line 30) accepts ASCII `-` only.
  `_parse_disabled_keys` also misses a bullet-prefixed URL that
  `parse_evidence_file` normalises (`fetcher.py` line 304). **Latent, not
  live** — I checked all four evidence files and none uses an en/em dash header
  or a bullet URL today. I don't know whether the extension can ever write one.
  Keep.
- **Ambiguous 2-digit-year dates are resolved by "latest year wins."**
  `harvester/utils.py` lines 265–279 and 291–304 pick `max()` of the two
  readings, and the DDMMYY branch (line 240) and `_YY_MM_DD_RE` branch skip
  `_is_plausible_bulletin_year` while five sibling branches apply it. So
  `27-08-26` reads as 2027-08-26, not 2026-08-27. `_is_plausible_bulletin_year`
  (line 187) also calls `date.today()`, so the same filename can parse
  differently depending on when harvest runs. The real fix is to resolve
  ambiguity against the harvest Sunday instead of by max-year, but
  `extract_date_from_string` takes no target. I found **no live parish** hitting
  this. Keep, and do not touch the locked `tests/test_cloud_folders.py` cases.
- `harvester/replay.py` `_insecure_ssl_context` (line 1539) retries with
  `CERT_NONE` for **any** host with a bad chain, not just mucknoparish.ie —
  while `host_profiles.json` already has an `ignore_https_errors` knob
  (`fetcher.py` line 613, `replay.py` line 3833) that this urllib path ignores.
  Cheap harden if Frank wants it; not urgent.
- `harvester/html_capture.py` line 340: `mode = "archive_nav_print" if navigated
  else "content_print"` where `navigated = page.url`, which is always truthy —
  so the logged capture mode is always `archive_nav_print`. Cosmetic log lie.
- `main.py` line 296 uses only the **first** diocese's contacts file for the
  combined mega PDF, so other dioceses fall back to key-derived display names.
  Cosmetic.

### Not the cause — say so out loud

- This is not an OCR-quality problem. Killanny, Raphoe parish and Sacred Heart
  were OCR'd **accurately**. The pipeline faithfully published the wrong
  document. Improving OCR will not fix any of the three.
- It is not a recipe-training problem either. All three recipes "work" — they
  fetch exactly what they were told to fetch.

---

## 23/08/2026 — Repo slick / this-week site

**The real goal, in one sentence:** the public site should show **this week only**,
and the repo should get slowly lighter — without breaking harvest, the mega PDF,
OCR, or recipes.

Audit only so far. Nothing was deleted, no cleanup PR was opened, no harvest was
run. Everything below was read on `origin/main` at commit `78063f98`.

### What is actually going on (proof, not opinion)

- **`docs/bulletins/` is the only folder on the site that piles up.** 182 files,
  19 MB. 12 of them are this week (`*-2026-08-23*.html`, four dioceses × three
  pages). The other 168 are old weeks going back to 20/05/2026 — 17 MB.
- **`docs/parishes/` does not pile up.** Its filenames have no date
  (`annagryparish.html`, `annagryparish.pdf`, …), so every harvest overwrites
  them. 458 files / 75 MB, all current week. Leave it alone.
- **The tap that fills the archive is `ocr-bulletin.yml`.** It writes
  `docs/bulletins/{diocese}-{TODAY}.html` (+`-ocr`, +`-pdf`) on every run and
  then commits with `git add docs`. `TODAY` is the day the OCR job ran, not the
  Sunday — which is why there are Wednesday and Thursday dates in there.
- **This week's twelve files are load-bearing.** `docs/index.html` links
  `bulletins/{diocese}-2026-08-23-ocr.html` for all four dioceses, and each
  `docs/dioceses/{diocese}/index.html` links both `-ocr.html` and `-pdf.html`.
  `harvester/site_builder.py` also reads the folder and picks the newest date
  (`_latest_viewer` line 431, `_latest_ocr_standalone` line 462,
  `_latest_pdf_standalone` line 1046). Delete the newest set and the homepage
  "read the text" buttons go 404.
- **No live page links to an old week.** Searching every dated `bulletins/…`
  reference in `docs/index.html`, all four diocese pages, `docs/subscribe/` and
  all 458 `docs/parishes/` pages returns only `2026-08-23`. So the 168 old files
  are reachable only by the archive index and by old bookmarks.
- **Harvest is not slow because of the archive.** Sunday's full harvest
  (run `32630174138`) took 70 minutes, and step 11 "Run Bulletin Harvester" was
  68 of those 70. Rebuilding the search index over the whole archive takes
  0.23 s. Do not sell the archive delete as a speed fix — it is a **site**
  fix (17 MB less deployed, 3.7 MB less downloaded by anyone using `/search/`).

### Two real bugs the audit turned up

1. **The harvest's own test gate has been dead.** `harvest.yml` line 103 runs
   bare `pytest`, which does not put the repo root on `sys.path`. In run
   `32630174138` step 8 finished in **0.36 s** with `collected 1 item / 5 errors`
   and `ModuleNotFoundError: No module named 'harvester'`; `pytest.ini` has
   `--maxfail=5` so collection stopped there. `continue-on-error: true` hid it.
   `test.yml` uses `python -m pytest`, which is why CI is green while the
   harvest gate is not. One-word fix.
2. **184 AI bulletin summaries fail on every OCR run.** Every file under
   `Bulletins/summaries/**` reads `{"bullets": null, "error":
   "summary_generation_failed"}` — 184 of 184. Nothing in the repo, the site, or
   the extension ever reads that folder. The loop in
   `ocr/generate_bulletin_pages.py` also `time.sleep(0.5)` between parishes, so
   this is ~92 s of sleeping plus 184 doomed API calls per OCR run. The code
   already has an off switch (`PARISH_AI_SUMMARIES_DISABLE=1`) that
   `ocr-bulletin.yml` never sets.

### NOW — small PRs Frank can say `go` to, one at a time

**N1. Turn off the tap (stop making new old-week pages).** ~4 files.
**Status 24/08/2026: done — PR [#115](https://github.com/Raphoe-Diocese/parish_harvester/pull/115) merged as `41c13064`, confirmed an ancestor of `origin/main` `1c7f7c60`.**
Add `prune_old_viewers()` to `ocr/generate_bulletin_pages.py` and call it from
`rebuild_indexes()` (already runs at the end of every viewer write). Rule: for
each diocese keep only the newest date's three files; never touch
`index.html` or subfolders. Prune **per diocese** so a diocese that has not been
regenerated yet does not lose its current page. Add one test. Update both lists.
*Risk if wrong:* a diocese page loses its OCR link. Guard with a test that the
newest trio survives.
*Built in PR #115:* `prune_old_viewers()` + `rebuild_indexes()` call it first;
`--regenerate-from` protects the date it just rewrote; `BULLETIN_PRUNE_DISABLE=1`
switches it off; 7 tests in `tests/test_bulletin_archive_prune.py`, including
`test_current_week_ocr_and_pdf_links_survive_prune` (site_builder still resolves
every diocese's `-ocr` / `-pdf` page after a prune). Dry run on a **copy** of the
real folder: 168 old pages removed, this week's 12 + `index.html` + the
`raphoe/` subfolder kept. Nothing in `docs/` was regenerated or deleted by that PR.
**Tick this done only after the PR is merged.**

**N2. Remove the 168 old-week pages that are already published.** 0 code files.
`git rm` every `docs/bulletins/*-<date>*.html` except the newest date per
diocese, then regenerate the index with
`python ocr/generate_bulletin_pages.py --rebuild-indexes`. Keep
`docs/bulletins/index.html` itself — `harvester/site_builder.py` line 1032 falls
back to it when a diocese has no viewer page. GitHub Pages drops the files on
the next deploy because `deploy-pages.yml` builds `_site` from `cp -a docs/.`.
*Risk if wrong:* old bookmarks 404. That is the intent.
*Do N1 first,* or the next OCR run just starts refilling.
**Status 24/08/2026: done — PR [#127](https://github.com/Raphoe-Diocese/parish_harvester/pull/127) merged as `7fb20550`, Pages [32678700149](https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/32678700149) success, live-proved.**
No hand-written `git rm` list: N1's own `prune_old_viewers()` did the delete via
`--rebuild-indexes`, so keep rule and delete rule are one piece of code. Counted
on `1c7f7c60` first instead of trusting the audit — 180 dated files in 60
diocese-date trios, newest `2026-08-23` for all four dioceses, so **168** old
files, exactly as audited. Left behind: 12 this-week pages, `index.html` rebuilt
from 60 links to 4, and `docs/bulletins/raphoe/index.html`. Also had to rebuild
`docs/search-index.json` — it was generated 29/07/2026 and all 999 of its
documents linked pages this PR deletes, which would have turned `/search/` into a
404 machine; it now holds 3 live `2026-08-23` documents. 0 broken dated
`bulletins/…` references anywhere under `docs/`; 50 tests green.
*Live-proved 24/08/2026.* Baseline first: all four old URLs were HTTP 200 live
before the merge. After merge + Pages they are HTTP **404** —
`bulletins/derry-2026-07-19.html`, `bulletins/down_and_connor-2026-05-20.html`,
`bulletins/raphoe-2026-08-21-ocr.html`, `bulletins/derry-2026-05-22-pdf.html`.
This week is untouched: HTTP 200 on all 12 pages, the homepage, `bulletins/` and
all four diocese pages; `bulletins/raphoe-2026-08-23-ocr.html` is 181,306 bytes,
titled `Raphoe Diocese Text Bulletin — 23/08/2026`, 24 parish headers, Irish
still Irish. Live `bulletins/` lists exactly 4 links. Live `/search/` is 200 with
3 documents and **0** dead links. `docs/bulletins/` on `main` is now 14 files.
Full evidence in `docs/WEBSITE_OCR_BACKLOG.md`.

**N3. Make the harvest test gate real.** 1 file, one word.
`.github/workflows/harvest.yml` line 103: `pytest -v --tb=short` →
`python -m pytest -v --tb=short`. Leave `continue-on-error: true` so a red test
still cannot stop a Sunday harvest — this only makes the warning honest.
*Risk if wrong:* none to harvest; worst case the step turns red and logs why.

### NEXT — after the three Now items land

- **Stop the 184 failing summaries.** Add `PARISH_AI_SUMMARIES_DISABLE: "1"` to
  the "Generate OCR viewer pages" env in `ocr-bulletin.yml`. 1 file. Then decide
  whether to delete the 188 write-only files in `Bulletins/summaries/` and the
  188 in `Bulletins/diffs/` (2 MB) — nothing reads either.
- **Delete `write_root_index()`** in `ocr/generate_bulletin_pages.py` (lines
  2569–2644, 76 lines). Nothing calls it — the only caller-shaped function,
  `rebuild_indexes()`, calls `write_bulletins_index()` only. If it ever did run
  it would overwrite the real homepage with the old "Parish Bulletin Dashboard"
  and a "Browse the full OCR bulletin archive" link;
  `tests/test_landing_page.py` line 140 asserts that link is *not* on the
  homepage.
- **Empty calendars.** All 186 files in `Bulletins/events/` have
  `"events": []`, so `docs/calendars/*.ics` are 159–181-byte empty shells last
  committed 30/07/2026. Either fix `harvester/events_extractor.py` or drop the
  calendars. Do not leave a dead subscribe link.
- **`docs/search-index.json` is stale and incomplete.** Last committed
  30/07/2026; 999 documents across 12 dates from May–July; Derry and Down &
  Connor only. Two causes: `harvest.yml` never stages it (line 411 stages
  `docs/manifest.json docs/index.html docs/dioceses/` and nothing else), and
  `harvester/manifest_builder.py` line 17 `VIEWER_FILE_PATTERN` omits `raphoe`.
  Same for `docs/reliability.json` (also built from a `recipes/learned/` folder
  that does not exist in the repo) and `docs/feeds/*.xml` (29/07/2026, no
  Clogher). Decide: fix, or stop publishing them.
- **Orphan pages** — reachable only from `docs/sitemap.html`, which nothing
  links to: `docs/badges/`, `docs/embed-examples.html`, `docs/search/`,
  `docs/calendars/`, `docs/feeds/`, `docs/audit/2026-05-22-deep-audit.md`.
  `docs/subscribe/` is linked by nothing at all. **I don't know whether Frank
  wants `/search/` — keep it** until he says. The one I would delete:
  `docs/bulletins/raphoe/index.html`, a hand-written stub from 27/06/2026 with
  24 hard-coded parish URLs, no generator, no inbound link, superseded by
  `docs/parishes/raphoe/` and `docs/dioceses/raphoe/`.
- **`Bulletins/all_bulletins_<date>.pages.json` accumulates** one per harvest
  week (2026-08-16 and 2026-08-23 today, 22 KB). `.gitignore` covers
  `Bulletins/all_bulletins_*.pdf` but not `.pages.json`. Add the pattern and
  drop the old one.

### KEEP — checked, do not touch

- `mega_pdf/` and `docs/mega_pdf/` (66 MB, four PDFs). Core. `HARVEST_MEGA_PDF=1`
  stays.
- `parishes/parish_status.json`, `parishes/recipes/` (163 files), `harvest.yml`,
  `harvester/fetcher.py`, `harvester/replay.py`, `extension/github_recipe_push.js`.
- The **113 loose `Bulletins/*.pdf`** (67 MB). They look like clutter but the
  extension's "View bulletin" fetches them —
  `extension/sidepanel.js` lines 1773 and 1875 build
  `…/main/Bulletins/{key}.pdf`.
- `docs/parishes/` (75 MB). Undated, overwritten weekly, already this-week only.
- `harvester/pattern_detector.py`. My first scan called it unused; it is
  imported by `harvester/fetcher.py` line 84 as a relative import
  (`from .pattern_detector import …`).
- `harvester/cost_tracker.py` and `harvester/retention.py`. No Python importer,
  but `harvest.yml` line 460 and `retention.yml` line 53 call them inline.
- **The extension.** All 22 JS/HTML files are referenced by something; no dead
  file found. `ph_recording_session` (singular) is a leftover, but
  `background.js` line 347, `recipe_diag_kit.js` line 358 and `content.js`
  line 142 read it deliberately as legacy data. No rewrite, no deletion.
- `harvester/scoreboard.py`, `scheduler.py`. Local dev helpers, off every
  workflow path. Harmless. **I don't know if Frank uses them — keep.**

### PARKED — do not start

- **Rewriting git history to shrink the repo.** `.git` is 734 MB. Deleting files
  from the tree does not shrink GitHub's quota. `git filter-repo` / BFG only
  after an explicit yes from Frank.
- **The 47 remote branches.** `cleanup_branches.yml` only matches `copilot/`
  and there are no `copilot/` branches, so it is a no-op today. Cosmetic.
- **Tidying the root markdown pile** (`CURSOR_LAST_RESULT.md`,
  `CURSOR_NEXT_TASK.md`, `FREE_SOLUTION.md`, `PROJECT_PLAN.md`,
  `CHECKPOINTS.md`, `DECISIONS_LOG.md`, `SITE_MAP.md` — most untouched since
  13/06/2026). Cosmetic. Not now.
- **Scaling to 26 dioceses.** `docs/dioceses/` already has 26 folders; 22 are
  ~1.6 KB placeholders. Stays parked per `AGENTS.md`.

### Not the cause — say so out loud

- The archive is not why harvest takes 70 minutes. The fetch step is.
- Local `_tmp_*` files on the Dynabook are **not** on GitHub. Nothing to delete
  there on the remote; just bin them locally.
