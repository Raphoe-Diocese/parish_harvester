"""How the harvester looks for a parish newsletter.

Learned tricks are the ones already proved on a real parish. Invented tricks
are new URL shapes the brain builds from the harvest Sunday. A trick is
remembered only when a probe brings back a real file and the freshness
referee accepts the date. An undated guess is not called fresh.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, urlunparse

from .bulletin_freshness import (
    FreshnessVerdict,
    check_bulletin_freshness,
    extract_bulletin_date_from_text,
    verdict_for_extracted_date,
)
from .liturgical import get_liturgical_name

MEMORY_PATH = Path(__file__).resolve().parent.parent / "parishes" / "newsletter_brain.json"

DIOCESE_ORDER = (
    "achonry",
    "ardagh",
    "armagh",
    "cashel_and_emly",
    "clogher",
    "cloyne",
    "cork_and_ross",
    "derry",
    "down_and_connor",
    "dromore",
    "dublin",
    "elphin",
    "ferns",
    "galway",
    "kerry",
    "kildare_and_leighlin",
    "killala",
    "killaloe",
    "kilmore",
    "limerick",
    "meath",
    "ossory",
    "raphoe",
    "tuam",
    "waterford_and_lismore",
)

# Ways already proved. The id is what a recipe site_type should use.
LEARNED = (
    {
        "id": "http_scrape_newest_pdf",
        "label": "Dated PDF link on the listing page",
        "how": "Score the filename date, not the /uploads/ year folder. On a bulletins list, take the Sunday named there. Twenty-Ninth for 18/10/2026. Milford and Rathmullan list Parish-Newsletter-Sunday-18th-October.pdf on https://milfordrathmullanparishes.ie/bulletins/. That name is 18/10/2026. A later notice date inside the file does not replace it. Do not keep a guessed Twenty-Sixth file. A PDF on dioceseofkerry.ie is the bulletin. The word diocese in the website name is not an admin document. Castleisland links 18th-October2026.pdf. Ferns parish names the weekend October-24th-October-25th-2026. That is 25/10/2026. The 25th is the Sunday, not the year 2018. Do not take 25th-October2026.pdf while the harvest Sunday is 18/10/2026. A file in an old uploads folder is still this Sunday when the filename says so, as at Crossmolina. A Mura fileID hash has the date in the link text. Cork family hubs are harvested once from the listing. Bearna's file is the Duilleog. Keep the Irish. Annagry's newsletter page lists 251025.pdf in /uploads/2026/10/. That is 25/10/2026. The trailing 25 is not the year 2025. An Spidéal lists 30ú Domhnach and 25 Deireadh Fómhair 2026 on cilleinde.ie. Deireadh Fómhair is October, so that file is 25/10/2026. Salthill lists Newsletter-25th-Oct-1.pdf. The 1 is the page, not the day. In the October 2026 folder that name is 25/10/2026. Navan's Sunday is in the /bulletin/ slug and the PDF is on the inner /s/ page. Do not pin /s/ or a fileID.",
    },
    {
        "id": "wp_json_newest_media",
        "label": "WordPress media library",
        "how": "Read /wp-json/wp/v2/media and take a newsletter source_url. The homepage can have no file while the media library has this Sunday. Carrigtwohill, Newmarket, Roscommon and Dingle were proved that way. Bree is www.bree.ie. Newsletter-3742-Oct-17th-18th.pdf is 18/10/2026. The 18th is the Sunday, not the year 2018. Skip the Oct 24th-25th JPEG while the harvest Sunday is 18/10/2026. When the harvest Sunday is 25/10/2026, that JPEG is this Sunday and the 17th-18th PDF is last week. Take the JPEG when it is newer than the PDF. Horeswood's page photo is named Thirtieth-Sunday-in-Ordinary-Time-2026. The referee reads that as 25/10/2026. Skip a JPEG preview. Keep Irish. Do not pin the dated name.",
    },
    {
        "id": "predicted_dated_pdf",
        "label": "Guess /pdf/DDMMYY.pdf",
        "how": "Listing HTML can be empty because the links are JavaScript. Tempo, Enniskillen, Longford and Beragh use /pdf/DDMMYY.pdf. Meath St Mary's Drogheda uses a3-bulletin-DD.MM.YYYY.pdf. St Senan's Enniscorthy uses n18october2026.pdf in the uploads folder. The current-newsletter link can already point at next Sunday. Kilmyshall, the Bunclody church, lists October-18th-2026.pdf. Keep the th. October-18-2026.pdf is the wrong name. Skip October-25th-2026.pdf while the harvest Sunday is 18/10/2026. A newer link on the same list must not replace this Sunday. Do not use the Church of Ireland Bunclody Union page. Ask for the harvest Sunday's name. Tawnawilly's file for 25/10/2026 is Sunday-25th-Oct.-26.pdf. The dot after Oct is part of the name. Sunday-25th-Oct-26.pdf is the wrong name. Prove the date from the file name. Do not pin it.",
    },
    {
        "id": "print_html_newsletter",
        "label": "Print the live HTML page",
        "how": "The page is overwritten each week. Do not pin a 109.228 article id. Mohill's newsletter is a WordPress page, not a post. Fenagh and Gortletteragh are inside that Mohill page. Kiltubrid /news/ is the same kind of overwritten page. Adamstown's diocese card has no file. The Website line is saintabbans.com. The Newsletters page lists 18th October, 2026 at the top. Open that page and print it. Do not pin ?p=1605.",
    },
    {
        "id": "wix_link_text_date",
        "label": "Wix hash with the date in the link text",
        "how": "Never save the /_files/ugd/ hash. Click the newest dated row. Irvinestown and Truagh. The date is in the link text.",
    },
    {
        "id": "onewebmedia_pdf",
        "label": "One.com onewebmedia PDF",
        "how": "Ignore an expired certificate and do not pin the hash. Lisnaskea and Galloon. An expired certificate is not a missing file.",
    },
    {
        "id": "dated_dotted_filename",
        "label": "DD.MM.YYYY or YY.MM.DD in the filename",
        "how": "Read the 4-digit year before a 2-digit year. Newsletter-23.08.2026.pdf and Kilronan DD.MM.YYYY.pdf.",
    },
    {
        "id": "rtf_newsletter",
        "label": "Weekly RTF converted to PDF",
        "how": "Take the newest .rtf. Do not invent a PDF name. Magheracloone 23rd-August-2026-.rtf.",
    },
    {
        "id": "image_stack",
        "label": "Sunday image, including an old upload folder",
        "how": "Stack the visible page images, including an img src. NextGEN gallery is not /uploads/. Fintona's Sunday image can sit in an old month folder. The filename date is the Sunday. Clonard scans the sheet as SKM_C550iYYMMDD. That is the scan day, not the Sunday. The front-page photo can already be next Sunday. Take the newest SKM scan dated on or before the harvest Sunday. On 18/10/2026 that is the 16/10/2026 scan, the sheet for Saturday 17 and Sunday 18 October. On 25/10/2026 the newest scan on or before Sunday is the 23/10/2026 scan, the sheet for Saturday 24 and Sunday 25 October. The 21/10/2026 scan is the development-fund results, not the newsletter. Do not pin the jpeg name.",
    },
    {
        "id": "jetpack_image",
        "label": "Jetpack i0.wp.com scan",
        "how": "Keep the i0.wp.com URL. Do not rewrite it back to the parish host.",
    },
    {
        "id": "cloud_folder_newest",
        "label": "Google Drive or OneDrive folder",
        "how": "Bruckless starts on the parent folder 1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK, then opens the folder named for the harvest year. In 2027 that year folder is new. Do not save the 2026 folder id 1z9goh6DrkCUkpJMDbwfsi28Yc_t0_ltC. Take the newest YY.MM.DD.pdf that is not after this Sunday. 26.10.18.pdf is 18/10/2026. The Drive file id has no date, so keep the name date. An older date inside the PDF must not replace it. Do not pin a /file/d/ link.",
    },
    {
        "id": "google_drive_static",
        "label": "One Drive file replaced each week",
        "how": "Irish Martyrs replaces one Drive file each week: /file/d/1m6sOGz3dECWvbbpXCnRGdHG77yWiLXxR. The title Newsletter 18th October 2026 is this Sunday. A later notice date is not the issue date. The day the file was uploaded is not the printed Sunday. Do not throw the bulletin out for that. Train on the /file/d/ preview, not the instant download link.",
    },
    {
        "id": "mcn_bulletin_date",
        "label": "Parish page that takes ?bulletin_date=",
        "how": "Add the harvest Sunday only when the URL itself has no date.",
    },
    {
        "id": "mdocs_table",
        "label": "mDocs PDF table",
        "how": "Click Download on the newest row. Use http when the certificate is dead.",
    },
    {
        "id": "joomla_dropfiles",
        "label": "Joomla Dropfiles docx",
        "how": "Click the parish cloud icon or the newest /Newsletters/NNN/ row at the top. Banagher 29/10/2026: homepage top id 406 is 25 Oct; a bottom/June pin left false stale. Skip diocese GDPR files. Do not pin the file id.",
    },
    {
        "id": "oneweb_docx",
        "label": "One.com Word file",
        "how": "Download the docx. Ignore slow Google preview iframes. view.officeapps.live.com?src= is the same Word file. A misspelled month such as Octaber still counts when the day and year are in the name. Claudy 28/10/2026: five-page Word weekly needs max_bulletin_pages 8.",
    },
    {
        "id": "sequential_bulletin_number",
        "label": "Numbered /Weekly-Bulletins/ folder",
        "how": "Advance the number by the weeks since the example.",
    },
    {
        "id": "parish_messenger",
        "label": "Parish Messenger widget",
        "how": "Wait for the JS widget. Click CLICK HERE to load Current Newsletter, then download use_captured_url. Same as Buncrana and Carndonagh. Do not fall back to a[href$=.pdf] on the page — Sion grabbed dead /pdf/090820.pdf. Skip Gift Aid, Data Entry, CatholicIreland readings. Melmount 29/10/2026: parishnews.html is already this week's HTML (no Messenger click) — print_to_pdf with skip_listing_nav. Sion shares that page; alias Sion to Melmount.",
    },
    {
        "id": "clonleigh_homepage_not_category",
        "when": "WordPress parish where /category/newsletter/ lags the homepage by a week",
        "how": "Start on the homepage. Click the top Strabane Pastoral Area Newsletter (or newest post title). print_to_pdf with skip_listing_nav. Do not trust Saturday-only URL prediction — Clonleigh 25/10/2026 published on Sunday /2026/10/25/. Try Sat then Sun folders if predicting.",
    },
    {
        "id": "wp_block_file",
        "label": "Permanent bulletin page, changing PDF name",
        "how": "Match *bulletin*.pdf. Never pin one week's filename.",
    },
    {
        "id": "shared_bulletin",
        "label": "Two parishes, one file",
        "how": "Download once. The other parish stays a labelled link. Moydow and Legan share one /pdf/ file. Kinvara and Ballinderreen share one file. St Nicholas and St Mary's Limerick share one file. Shannon West is one file for several parishes. Harvest once.",
    },
    {
        "id": "dead_hostname_twin",
        "label": "Official hostname is dead",
        "how": "Try the live .ie .com or .co.uk twin. Skip Anglican twins. Kilronan's official host is dead. The live site is parishofkilronan.ie. parishardaghmoydow.com is dead. The live site is ardaghmoydow.com.",
    },
    {
        "id": "facebook_link_only",
        "label": "Facebook or Instagram only",
        "how": "Leave a clickable link. Do not scrape the post.",
    },
    {
        "id": "mayo_ie_getmedia",
        "label": "Mayo County Council parish newsletter list",
        "how": "Open /en-ie/parish-newsletters/{name}-parish-newsletter or the plural. Take the newest /getmedia/ PDF. A diocese profile page is not the bulletin.",
    },
    {
        "id": "connect_news_article",
        "label": "Parish site NEWS.aspx article",
        "how": "Read ArticleDetail.aspx links titled Parish Newsletter. The date is in the link text. Print that article. Do not save the diocese /parishes/ page.",
    },
    {
        "id": "http_pdf_after_browser_abort",
        "label": "Plain HTTP download when the browser aborts a PDF",
        "how": "ERR_ABORTED on a PDF is not a missing file. Read the listing and take sunday-newsletter-DD-MM-YYYY for this Sunday. Prefer the parish file over thought-for-the-week. Download it with plain HTTP.",
    },
    {
        "id": "dated_bulletin_post",
        "label": "WordPress post whose address contains the Sunday date",
        "how": "Open /parish-bulletin-18th-october-2026/ from the homepage. The picture is an img src on that post, not a link on the homepage. A category page with no PDF can still link emly-parish-bulletin-18th-october-2026. Open that post and take the Word file.",
    },
    {
        "id": "permanent_bulletin_pdf",
        "label": "Same bulletin.pdf address every week",
        "how": "Newtown Killea replaces https://newtownkilleaparish.ie/wp-content/uploads/parish-bulletins/unassigned/raphoe/newtown-killea/bulletin.pdf each week. Take that file. Do not date it from the HTML page. Templecrone's Drive file was last changed on 14/09/2026. The weekly file is https://templecroneparish.ie/wp-content/uploads/parish-bulletins/unassigned/raphoe/templecrone/bulletin.pdf and it was updated on 24/10/2026. Annagry's newsletter page dropped 251025.pdf. The weekly file is https://annagryparish.ie/wp-content/uploads/parish-bulletins/raphoe/raphoe/annagry/bulletin.pdf and it was updated on 24/10/2026. Do not use the unassigned folder for Annagry. A /current-newsletter/ address that redirects to this week's PDF is the same idea. Kildare, Meath Athboy, Dunshaughlin, Kells, Kilbeggan, Limerick St Joseph's, and Derry Bellaghy. Always set disable_stale_rescrape_fallback. When the redirect is last week, leave it stale — never homepage-rescrape (Bellaghy pope-francis jpeg). Do not pin the dated file it redirects to.",
    },
    {
        "id": "sunday_named_upload",
        "label": "This Sunday's file name on the uploads folder",
        "how": "When the homepage has no file, try the uploads folder for this Sunday. Cloyne is Newsletter-18th-October-2026-29th-Sunday-in-Ordinary-Time.pdf. Crumlin is 2026-10-18-Newsletter.pdf. Wexford is Sunday-October-18th-1-scaled.jpg and the next page numbers. Falcarragh on 18/10/2026 is Parish-Newsletter-42-Sun-A-18102026.pdf. The 25/10/2026 file is Parish-Newsletter-43for-Sun-A-25102026.pdf. There is no hyphen before for. A 403 forbidden page is not a missing file. Cloyne 24/10/2026: urllib got that page and the browser got the PDF. The same page on another parish is the same trick.",
    },
)


def stored_steps() -> tuple[dict, ...]:
    """Proved steps for finding a website and a bulletin.

    This is the list the recipe brain reads. Hunt notes are copied in here.
    """
    return LEARNED

_HREF_RE = re.compile(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I)
_MEDIA_RE = re.compile(
    r"""(?:href|src|data-src)\s*=\s*['"]([^'"]+)['"]""",
    re.I,
)
_DATED_POST_RE = re.compile(
    r"""href\s*=\s*['"]([^'"]*(?:bulletin|newsletter)[^'"]*)['"]""",
    re.I,
)
_OFFICE_SRC_RE = re.compile(
    r"officeapps\.live\.com/op/embed\.aspx\?src=([^\"'\s&]+)",
    re.I,
)
_SKIP_RE = re.compile(
    r"gdpr|gift[\s-]?aid|privacy|financial|data[\s-]?entry|new[\s-]?parishioner|"
    r"safeguarding|rota|vocation|anglican",
    re.I,
)
_FACEBOOK_RE = re.compile(r"facebook\.com|instagram\.com|fb\.com", re.I)
_POINTER_RE = re.compile(r"churchservices\.tv", re.I)
_FILE_RE = re.compile(r"\.(?:pdf|docx|doc|rtf|jpe?g|png)(?:$|\?)", re.I)
_ARTICLE_RE = re.compile(
    r'href="(ArticleDetail\.aspx\?articleid=\d+)"[^>]*>\s*(Parish\s+Newsletter[^<]{0,80})',
    re.I,
)
_GETMEDIA_RE = re.compile(
    r'href="(/getmedia/[^"]+\.pdf)"[^>]*>\s*([^<]+)',
    re.I,
)
_SIDE_PDF_RE = re.compile(r"thought-for-the-week|pastoral-letter", re.I)
_BULLETIN_WORD_RE = re.compile(r"newsletter|bulletin|parish[\s-]?news", re.I)
_DRIVE_NAME_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{2}\.pdf)\b", re.I)
_UPLOADS_RE = re.compile(r"/uploads/(20\d{2})/(0?\d{1,2})/", re.I)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass
class Candidate:
    strategy_id: str
    url: str
    kind: str
    why: str
    label: str = ""


@dataclass
class Win:
    strategy_id: str
    url: str
    parish_key: str
    verdict: str
    bulletin_date: str
    file_kind: str


def diocese_order() -> tuple[str, ...]:
    return DIOCESE_ORDER


def next_diocese(done: set[str] | list[str]) -> str | None:
    finished = {str(item).strip().lower() for item in done}
    for key in DIOCESE_ORDER:
        if key not in finished:
            return key
    return None


def referee(url: str, body_text: str, target: date) -> FreshnessVerdict:
    """Date check. A newer link date beats an older date in the file.

    An undated link stays unknown. A stale heading in the file then wins.
    Do not call an undated link fresh because the file mentions a date.
    """
    link = check_bulletin_freshness(url or "", target)
    body_date = extract_bulletin_date_from_text(body_text or "")
    body = verdict_for_extracted_date(body_date, target) if body_date else None

    if link.extracted_date and body and body.extracted_date:
        if link.extracted_date > body.extracted_date and link.status == "fresh":
            return FreshnessVerdict(
                status="fresh",
                extracted_date=link.extracted_date,
                reason="link_date_beats_older_body",
                days_from_target=link.days_from_target,
            )
        return link

    if link.status == "unknown" and body and body.status == "stale":
        return FreshnessVerdict(
            status="stale",
            extracted_date=body.extracted_date,
            reason="undated_url_stale_body",
            days_from_target=body.days_from_target,
        )
    if link.status == "unknown":
        return FreshnessVerdict(status="unknown", reason="no_date_in_url")
    return link


def _origin(page_url: str) -> str:
    parsed = urlparse(page_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _rejected(url: str) -> bool:
    if _FACEBOOK_RE.search(url) or _POINTER_RE.search(url):
        return True
    if _SKIP_RE.search(url):
        return True
    if "/_files/ugd/" in url.lower():
        return True
    return False


def _abs(page_url: str, href: str) -> str:
    return urljoin(page_url, href.strip())


def filename_shapes(target: date) -> list[str]:
    """New filename guesses for one Sunday. Each one carries a real date."""
    day, month, year = target.day, target.month, target.year
    names = [
        f"{day:02d}{month:02d}{year % 100:02d}.pdf",
        f"{day:02d}{month:02d}{year}.pdf",
        f"{year}-{month:02d}-{day:02d}.pdf",
        f"{day:02d}.{month:02d}.{year}.pdf",
        f"{year % 100:02d}.{month:02d}.{day:02d}.pdf",
        f"Sunday-{_ordinal(day)}-{_MONTHS[month - 1]}-{year % 100:02d}.pdf",
    ]
    liturgical = get_liturgical_name(target)
    full_month = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )[month - 1]
    ordered = _ordinal(day)
    if liturgical:
        names.append(liturgical.replace("_", "-") + ".pdf")
        names.insert(
            0,
            f"Newsletter-{ordered}-{full_month}-{year}-"
            f"{liturgical.replace('_', '-')}.pdf",
        )
    names.insert(0, f"{year}-{month:02d}-{day:02d}-Newsletter.pdf")
    names.append(f"Sunday-{full_month}-{ordered}-1-scaled.jpg")
    names.append(f"n{day}{full_month.lower()}{year}.pdf")
    return names


def predicted_urls(page_url: str, target: date) -> list[Candidate]:
    origin = _origin(page_url)
    if not origin:
        return []
    folders = (
        "/pdf/",
        f"/wp-content/uploads/{target.year}/{target.month:02d}/",
    )
    found: list[Candidate] = []
    for folder in folders:
        for name in filename_shapes(target):
            found.append(
                Candidate(
                    strategy_id="predicted_dated_pdf",
                    url=origin + folder + name,
                    kind="invented",
                    why="Sunday filename on a usual bulletin folder",
                )
            )
    found.append(
        Candidate(
            strategy_id="wp_json_newest_media",
            url=origin + "/wp-json/wp/v2/media?search=newsletter&per_page=10",
            kind="invented",
            why="WordPress media search for newsletter",
        )
    )
    if "bulletin_date=" not in page_url:
        found.append(
            Candidate(
                strategy_id="mcn_bulletin_date",
                url=page_url.split("?")[0] + f"?bulletin_date={target.isoformat()}",
                kind="invented",
                why="Ask the parish page for the harvest Sunday",
            )
        )
    return found


def is_diocese_profile(url: str) -> bool:
    """A diocese /parishes/ card is the parish's address, not its newsletter."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    return "/parishes/" in parsed.path.lower() and "diocese" in host


def parish_slug_from_profile(url: str) -> str:
    part = urlparse(url or "").path.rstrip("/").split("/")[-1]
    return re.sub(r"-\d+$", "", part).strip().lower()


def profile_probes(url: str) -> list[Candidate]:
    """Where to look after a diocese profile was saved instead of a newsletter."""
    slug = parish_slug_from_profile(url)
    if not slug:
        return []
    found: list[Candidate] = []
    base = "https://www.mayo.ie/en-ie/parish-newsletters/"
    for path in (f"{slug}-parish-newsletters", f"{slug}-parish-newsletter"):
        found.append(
            Candidate(
                strategy_id="mayo_ie_listing",
                url=base + path,
                kind="invented",
                why="Mayo council list for this parish name",
            )
        )
    compact = slug.replace("-", "")
    found.append(
        Candidate(
            strategy_id="connect_news_list",
            url=f"https://www.{compact}.com/NEWS.aspx",
            kind="invented",
            why="Parish news list on the parish's own site",
        )
    )
    return found


def parse_connect_news(html: str, page_url: str) -> list[Candidate]:
    """Article links whose text is Parish Newsletter plus a date."""
    found: list[Candidate] = []
    for href, title in _ARTICLE_RE.findall(html or ""):
        label = " ".join(title.split())
        found.append(
            Candidate(
                strategy_id="connect_news_article",
                url=_abs(page_url, href),
                kind="learned",
                why="Parish Newsletter article on the parish site",
                label=label,
            )
        )
    return found


def parse_mayo_listing(html: str, page_url: str) -> list[Candidate]:
    """Newest-looking PDFs on a Mayo.ie parish newsletter page."""
    found: list[Candidate] = []
    for href, title in _GETMEDIA_RE.findall(html or ""):
        label = " ".join(title.split())
        if not _BULLETIN_WORD_RE.search(label):
            continue
        found.append(
            Candidate(
                strategy_id="mayo_ie_getmedia",
                url=_abs(page_url, href),
                kind="learned",
                why="PDF linked from the Mayo council newsletter list",
                label=label,
            )
        )
    return found


def neighbour_month_urls(url: str) -> list[Candidate]:
    match = _UPLOADS_RE.search(url or "")
    if not match:
        return []
    year = int(match.group(1))
    month = int(match.group(2))
    found: list[Candidate] = []
    for shift in (-1, 1):
        moved = month + shift
        moved_year = year
        if moved < 1:
            moved = 12
            moved_year -= 1
        elif moved > 12:
            moved = 1
            moved_year += 1
        new_url = _UPLOADS_RE.sub(
            f"/uploads/{moved_year}/{moved:02d}/",
            url,
            count=1,
        )
        found.append(
            Candidate(
                strategy_id="neighbour_month_folder",
                url=new_url,
                kind="invented",
                why="Same filename in the month beside the upload folder",
            )
        )
    return found


def pick_from_wp_json(items: list[dict], target: date) -> Candidate | None:
    best: Candidate | None = None
    for item in items:
        source = str(item.get("source_url") or "")
        if not source or _rejected(source):
            continue
        verdict = check_bulletin_freshness(source, target)
        if verdict.status != "fresh":
            continue
        title = str(item.get("title") or "")
        if title and _SKIP_RE.search(title):
            continue
        best = Candidate(
            strategy_id="wp_json_newest_media",
            url=source,
            kind="invented",
            why="Media library file dated in this harvest week",
        )
        break
    return best


def links_on_page(html: str, page_url: str) -> list[Candidate]:
    if not html:
        return []
    found: list[Candidate] = []
    seen: set[str] = set()
    has_file = False
    for match in _MEDIA_RE.finditer(html):
        href = match.group(1).strip()
        if not href or href.startswith("#"):
            continue
        url = _abs(page_url, href)
        if url in seen or _rejected(url):
            continue
        if not _FILE_RE.search(url):
            continue
        seen.add(url)
        has_file = True
        strategy = "http_scrape_newest_pdf"
        if "i0.wp.com" in url.lower():
            strategy = "jetpack_image"
        elif url.lower().endswith(".rtf") or ".rtf?" in url.lower():
            strategy = "rtf_newsletter"
        elif re.search(r"\.(jpe?g|png)(?:$|\?)", url, re.I):
            strategy = "image_stack"
        found.append(
            Candidate(
                strategy_id=strategy,
                url=url,
                kind="learned",
                why="File link already on the page",
            )
        )
    for name in _DRIVE_NAME_RE.findall(html):
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        found.append(
            Candidate(
                strategy_id="cloud_folder_newest",
                url=name,
                kind="learned",
                why="Drive row named YY.MM.DD.pdf",
            )
        )
    for match in _DATED_POST_RE.finditer(html):
        url = _abs(page_url, match.group(1).strip())
        if url in seen or _rejected(url) or _FILE_RE.search(url):
            continue
        if check_bulletin_freshness(url, date(2026, 1, 1)).extracted_date is None:
            continue
        seen.add(url)
        found.append(
            Candidate(
                strategy_id="dated_bulletin_post",
                url=url,
                kind="learned",
                why="Bulletin post address contains a Sunday date",
            )
        )
    if not has_file and _BULLETIN_WORD_RE.search(html):
        found.append(
            Candidate(
                strategy_id="print_html_newsletter",
                url=page_url,
                kind="learned",
                why="Newsletter words on the page and no file to download",
            )
        )
    return found


_SECTION_RE = re.compile(
    r"/(?:newsletters?|nuachtlitir|parish-bulletin|weekly-bulletins|bulletins)/?$",
    re.I,
)


def section_links(html: str, page_url: str) -> list[str]:
    """Undated newsletter index on the same site. Crumlin hides the PDF there."""
    if not html:
        return []
    host = (urlparse(page_url).netloc or "").lower()
    found: list[str] = []
    seen: set[str] = set()
    for match in _MEDIA_RE.finditer(html):
        href = match.group(1).strip()
        if not href or href.startswith("#"):
            continue
        url = _abs(page_url, href)
        parsed = urlparse(url)
        if host and parsed.netloc.lower() != host:
            continue
        if not _SECTION_RE.search(parsed.path or ""):
            continue
        if url in seen or _rejected(url):
            continue
        seen.add(url)
        found.append(url)
    return found


def parse_office_embed(html: str) -> list[Candidate]:
    """The Word file is hidden in a Microsoft Office preview address."""
    found: list[Candidate] = []
    seen: set[str] = set()
    for match in _OFFICE_SRC_RE.finditer(html or ""):
        url = unquote(match.group(1))
        if url in seen or _rejected(url) or not _FILE_RE.search(url):
            continue
        seen.add(url)
        kind = "oneweb_docx" if re.search(r"\.docx(?:$|\?)", url, re.I) else "http_scrape_newest_pdf"
        found.append(
            Candidate(
                strategy_id=kind,
                url=url,
                kind="learned",
                why="Office embed src is the parish file",
            )
        )
    return found


def invent_candidates(html: str, page_url: str, target: date) -> list[Candidate]:
    """Page links first, then new guesses. Facebook is never a guess."""
    page = links_on_page(html, page_url)
    page.extend(parse_connect_news(html, page_url))
    page.extend(parse_mayo_listing(html, page_url))
    page.extend(parse_office_embed(html))
    file_urls = [item.url for item in page if _FILE_RE.search(item.url)]
    # A listing PDF is enough. Do not also open a /bulletin/ path.
    if file_urls:
        page = [item for item in page if "/bulletin/" not in item.url.lower() or _FILE_RE.search(item.url)]
    if is_diocese_profile(page_url):
        guessed = profile_probes(page_url)
    else:
        guessed = predicted_urls(page_url, target)
    for item in page:
        guessed.extend(neighbour_month_urls(item.url))
    combined = page + guessed
    unique: list[Candidate] = []
    seen: set[str] = set()
    for item in combined:
        if item.url in seen or _rejected(item.url):
            continue
        seen.add(item.url)
        unique.append(item)
    return unique


_PROBE_STRATEGIES = {
    "wp_json_newest_media",
    "print_html_newsletter",
    "mcn_bulletin_date",
    "mayo_ie_listing",
    "connect_news_list",
}


def candidate_verdict(
    item: Candidate, target: date, body_text: str = ""
) -> FreshnessVerdict:
    """Date the file. A Parish Newsletter title counts when the URL has no date."""
    url_verdict = check_bulletin_freshness(item.url, target)
    if url_verdict.status != "unknown":
        return referee(item.url, body_text, target)
    label = (item.label or "").strip()
    if label and _BULLETIN_WORD_RE.search(label):
        labelled = check_bulletin_freshness(label, target)
        if labelled.status != "unknown":
            return labelled
    return referee(item.url, body_text, target)


def weekend_files(candidates: list[Candidate], target: date) -> list[Candidate]:
    """This Sunday's real files, uploads folder before a bare /pdf/ guess."""
    picked: list[Candidate] = []
    for item in candidates:
        if item.strategy_id in _PROBE_STRATEGIES:
            continue
        if not _FILE_RE.search(item.url or ""):
            continue
        extracted = candidate_verdict(item, target).extracted_date
        if extracted is None:
            continue
        if not (target - timedelta(days=1) <= extracted <= target):
            continue
        picked.append(item)

    # thought-for-the-week can carry this Sunday's date and still not be
    # the parish bulletin. Edgeworthstown 24/10/2026 saved that file first.
    parish_files = [item for item in picked if not _SIDE_PDF_RE.search(item.url)]
    if parish_files:
        picked = parish_files

    def _rank(item: Candidate) -> tuple[int, int, int]:
        url = item.url.lower()
        return (
            0 if item.kind == "learned" else 1,
            0 if "/wp-content/uploads/" in url else 1,
            0 if any(word in url for word in ("newsletter", "bulletin", "sunday")) else 1,
        )

    picked.sort(key=_rank)
    return picked


def pick_same_day_file(urls: list[str], patterns: list[str] | None = None) -> str | None:
    """Several files can share this Sunday. Keep the parish file.

    thought-for-the-week can be dated this Sunday and still not be the bulletin.
    A pattern that only sits in the website name matches every file on that site.
    Prefer the pattern that is in the file path.
    """
    if not urls:
        return None
    real = [url for url in urls if not _SIDE_PDF_RE.search(url)]
    pool = real or list(urls)
    pats = [p.lower() for p in (patterns or []) if p]

    def path_score(url: str) -> int:
        path = unquote(urlparse(url).path).lower()
        hits = [len(pat) for pat in pats if pat in path]
        return max(hits) if hits else 0

    pool.sort(key=path_score, reverse=True)
    return pool[0]


def same_sunday_urls(scored: list[tuple[date, str]], target: date) -> list[str]:
    """Next Sunday's file is not this Sunday's bulletin.

    Castleisland lists 4 Oct, 18 Oct and 25 Oct. For harvest Sunday 18/10/2026
    the file is 18th-October2026.pdf.
    """
    on_or_before = [(found, url) for found, url in scored if found <= target]
    if not on_or_before:
        return []
    best = max(found for found, _url in on_or_before)
    return [url for found, url in on_or_before if found == best]


def choose(candidates: list[Candidate], target: date, body_text: str = "") -> Candidate | None:
    """First fresh file. A stale file is kept only if nothing this week exists."""
    fresh: list[tuple[Candidate, FreshnessVerdict]] = []
    stale: list[tuple[Candidate, FreshnessVerdict]] = []
    for item in candidates:
        if item.strategy_id in _PROBE_STRATEGIES:
            continue
        verdict = candidate_verdict(item, target, body_text)
        if verdict.status == "fresh":
            fresh.append((item, verdict))
        elif verdict.status == "stale":
            stale.append((item, verdict))
    def _closest(pairs: list[tuple[Candidate, FreshnessVerdict]]) -> Candidate:
        pairs.sort(
            key=lambda pair: (
                2 if _SIDE_PDF_RE.search(pair[0].url) else 1 if pair[0].strategy_id == "dated_bulletin_post" else 0,
                abs(pair[1].days_from_target or 99),
            )
        )
        return pairs[0][0]

    learned_fresh = [pair for pair in fresh if pair[0].kind == "learned"]
    learned_stale = [pair for pair in stale if pair[0].kind == "learned"]
    if learned_fresh:
        return _closest(learned_fresh)
    if learned_stale:
        return _closest(learned_stale)
    if fresh:
        return _closest(fresh)
    if stale:
        return _closest(stale)
    for item in candidates:
        if item.strategy_id == "print_html_newsletter":
            return item
    return None


def proved_win(
    candidate: Candidate,
    *,
    http_status: int,
    file_kind: str,
    verdict: FreshnessVerdict,
    parish_key: str,
) -> Win | None:
    """A guess becomes a win only with a real file and a date verdict."""
    if http_status != 200:
        return None
    if file_kind not in {"pdf", "html", "image", "rtf", "docx"}:
        return None
    if verdict.status not in {"fresh", "stale"}:
        return None
    if _rejected(candidate.url):
        return None
    if verdict.status == "fresh" and verdict.extracted_date is None:
        return None
    when = verdict.extracted_date.isoformat() if verdict.extracted_date else ""
    return Win(
        strategy_id=candidate.strategy_id,
        url=candidate.url,
        parish_key=parish_key,
        verdict=verdict.status,
        bulletin_date=when,
        file_kind=file_kind,
    )


def remember(win: Win, path: Path | None = None) -> dict:
    """Append a proved win. The same parish and strategy is not stored twice."""
    target = path or MEMORY_PATH
    memory = {"version": 1, "wins": []}
    if target.is_file():
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("wins"), list):
            memory = loaded
    wins = memory.setdefault("wins", [])
    row = asdict(win)
    for existing in wins:
        if (
            existing.get("parish_key") == row["parish_key"]
            and existing.get("strategy_id") == row["strategy_id"]
            and existing.get("url") == row["url"]
        ):
            return memory
    wins.append(row)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(memory, indent=2), encoding="utf-8")
    return memory
