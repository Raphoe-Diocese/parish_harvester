"""Recipe Brain — remember which hub trick won, reuse it on the next parish.

24/7 skip-parish hub scan runs on GitHub Actions
(`.github/workflows/recipe-brain-hunt.yml`), not on Frank's laptop.
hint_for_url() is click-memory: one proved host must suggest the same
recipe shape for the next similar URL. remember_win() writes the trick
back into parishes/site_patterns.json.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from harvester.config import BASE_DIR, target_sunday
from harvester.utils import extract_date_from_string, format_uk_date

PATTERNS_PATH = BASE_DIR / "parishes" / "site_patterns.json"
RECIPES_DIR = BASE_DIR / "parishes" / "recipes"
CURSOR_PATH = BASE_DIR / "parishes" / "recipe_brain_cursor.json"
UA = "ParishPress-RecipeBrain/1.0 (+https://www.parishpress.ie/)"

_SKIP_HOSTS = {
    "facebook.com",
    "m.facebook.com",
    "www.facebook.com",
    "fb.watch",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
}
_DIRECTORY_HOSTS = {
    "dublindiocese.ie",
    "www.dublindiocese.ie",
    "vocations.ie",
    "www.vocations.ie",
    "catholicbishops.ie",
    "www.catholicbishops.ie",
}

_HREF_PDF_RE = re.compile(
    r"""href=["']([^"']+\.pdf[^"']*)["']""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HubHint:
    """A remembered trick for a bulletin host."""

    key: str
    site_type: str
    label: str
    confidence: str
    notes: tuple[str, ...]
    do_not: tuple[str, ...]
    pattern_key: str = ""


def _host(url: str) -> str:
    host = urlparse((url or "").strip()).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def hint_for_url(url: str) -> HubHint | None:
    """Return the remembered hub trick for *url*, or None."""
    raw = (url or "").strip()
    if not raw:
        return None
    host = _host(raw)
    path = urlparse(raw).path.lower()

    if host in {"mcn.live", "www.mcn.live"} or "mcn.live" in host:
        return HubHint(
            key="mcn_live",
            site_type="mcn_live_parish_page",
            label="MCN camera page newsletter (JSON, not the webcam)",
            confidence="high",
            notes=(
                "Newsletter sits on the MCN camera page. Harvest uses the profile JSON, not the stream.",
                "Start at the /Camera/ URL Frank trained. Do not pin a dated PDF.",
            ),
            do_not=(
                "Do not harvest the webcam video.",
                "Do not pin a dated newsletter filename.",
            ),
            pattern_key="mcn_live+direct_download",
        )

    if host == "churchmedia.tv":
        return HubHint(
            key="churchmedia",
            site_type="churchmedia_newsletter",
            label="churchmedia.tv latest newsletter button",
            confidence="high",
            notes=(
                "Use getChannelAbout for this week's PDF. Portaferry proved this.",
                "The public /newsletter/<token> path dies on the next upload.",
            ),
            do_not=("Do not pin churchmedia /newsletter/<token>.….pdf.",),
            pattern_key="churchmedia+direct_download",
        )

    if host == "mayo.ie" or path.startswith("/getmedia/"):
        return HubHint(
            key="mayo_ie",
            site_type="http_scrape_newest_pdf",
            label="Mayo County Council parish-newsletters listing",
            confidence="high",
            notes=(
                "Hub https://www.mayo.ie/parish-newsletter — Google/WebSearch finds it. Many Mayo cards with DD-MM-YYYY (Frank 29/10/2026).",
                "Belmullet proved GET 200 on mayo.ie parish-newsletters. Date is in the link text and filename.",
                "Scrape the listing each week. The getmedia GUID changes. Use for Killala/Tuam/Achonry leftovers.",
            ),
            do_not=(
                "Do not pin the getmedia GUID.",
                "Do not treat a PNG as a PDF recipe.",
                "Do not skip mayo.ie when the diocese card has no file.",
            ),
            pattern_key="mayo_ie+direct_download",
        )

    if host in {"churchservices.tv", "www.churchservices.tv"}:
        return HubHint(
            key="churchservices_tv",
            site_type="link_only",
            label="churchservices.tv webcam — pointer only until a newsletter file is proved",
            confidence="low",
            notes=(
                "Webcam first. Look on the same page for a newsletter link. Else keep the real parish site.",
            ),
            do_not=(
                "Do not harvest the livestream as a bulletin.",
                "Do not invent a PDF because a webcam exists.",
            ),
            pattern_key="churchservices_tv+pointer",
        )

    if host in {"theparishioner.ie", "onefaith.ie"} or "/images/newsletter/" in path:
        return HubHint(
            key="joomla_images_newsletter",
            site_type="http_scrape_newest_pdf",
            label="Joomla /images/newsletter/YY-MM-DD.pdf listing",
            confidence="high",
            notes=(
                "Listing HTML links /images/newsletter/YY-MM-DD.pdf. That file is the bulletin.",
                "31/10/2026 theparishioner.ie proved 26-10-25.pdf (25/10/2026) and 26-11-01.pdf (01/11/2026).",
                "The HTML article /newsletter/the-parishioner-… is not the PDF.",
                "Same shape on onefaith.ie. 31/10/2026 newest proved file was 26-10-12.pdf (12/10/2026), behind target.",
            ),
            do_not=(
                "Do not pin YY-MM-DD.pdf.",
                "Do not print the HTML article as the bulletin.",
                "Do not call onefaith fresh while its newest PDF is 12/10/2026.",
            ),
            pattern_key="joomla_images_newsletter+direct_download",
        )

    if host == "arklowparish.ie":
        return HubHint(
            key="homepage_bracket_date",
            site_type="http_scrape_newest_pdf",
            label="Homepage PDF with [YYYY-MM-DD] in the filename",
            confidence="high",
            notes=(
                "31/10/2026 the Arklow homepage linked newsletter_1st_November_2026[2026-11-01].pdf.",
                "Proved application/pdf, %PDF-1.7, date 01/11/2026. The date in square brackets is the bulletin date.",
                "The recipe already scrapes the homepage. The 25/10 harvest failed because that file was not there yet.",
            ),
            do_not=("Do not pin the dated homepage PDF.",),
            pattern_key="homepage_bracket_date+direct_download",
        )

    if host == "armaghparish.net":
        return HubHint(
            key="yearless_month_pdf",
            site_type="http_scrape_newest_pdf",
            label="Yearless Month PDF under /YYYY/MM/",
            confidence="high",
            notes=(
                "31/10/2026 the Armagh listing newest file was 18th-October.pdf under /2026/10/.",
                "The filename has no year. The folder year is 2026. That file is behind the 25/10 target.",
                "Leave it stale. Do not pin 27 September and do not pin 18 October.",
            ),
            do_not=(
                "Do not pin 18th-October.pdf.",
                "Do not pin the older 27 September file.",
            ),
            pattern_key="yearless_month_pdf+direct_download",
        )

    if host == "stbrendansbirr.ie":
        return HubHint(
            key="ddmmyyyy_listing_pdf",
            site_type="http_scrape_newest_pdf",
            label="Listing PDF named DDMMYYYY.pdf",
            confidence="high",
            notes=(
                "31/10/2026 Birr /newsletter/ linked 01112026.pdf and 25102026.pdf.",
                "Proved both application/pdf. The filename is DDMMYYYY. Do not pin it.",
                "Harvest 41227670229 ok. Saved 25102026.pdf. Date 25/10/2026. This Sunday won.",
            ),
            do_not=("Do not pin the DDMMYYYY.pdf name.",),
            pattern_key="ddmmyyyy_listing_pdf+direct_download",
        )

    if host == "bodyketuamgraneyparish.ie":
        return HubHint(
            key="spelled_month_listing_pdf",
            site_type="http_scrape_newest_pdf",
            label="Listing PDF named Month-Dth-YYYY",
            confidence="high",
            notes=(
                "31/10/2026 Bodyke /newsletter/ linked November-1st-2026 and October-25th-2026 PDFs.",
                "Proved both application/pdf. /parish-newsletter/ was a 404. Use /newsletter/.",
                "Harvest 41227674612 ok. Saved the October-25th-2026 PDF. Date 25/10/2026.",
            ),
            do_not=("Do not pin the dated filename.", "Do not use the 404 /parish-newsletter/ path."),
            pattern_key="spelled_month_listing_pdf+direct_download",
        )

    if host == "dioceseofkerry.ie":
        return HubHint(
            key="kerry_card_yyyymmdd_pdf",
            site_type="http_scrape_newest_pdf",
            label="Kerry diocese card PDF named YYYY-MM-DD.pdf",
            confidence="high",
            notes=(
                "The parish card on dioceseofkerry.ie links this week's PDF. Do not pin it.",
                "31/10/2026 Baile an Fheirtearaigh card proved 2026-11-01.pdf (application/pdf, 01/11/2026).",
                "31/10/2026 Boherbue's card first page still showed August files. That one stays stale.",
            ),
            do_not=(
                "Do not pin the dated PDF.",
                "Do not use the diocese Facebook page as the parish link.",
                "Do not save the /parish/ card as the bulletin.",
            ),
            pattern_key="kerry_card_yyyymmdd_pdf+direct_download",
        )

    if host == "bree.ie":
        return HubHint(
            key="wp_json_weekend_range_pdf",
            site_type="wp_json_newest_media",
            label="Bree weekend PDF in the media library",
            confidence="high",
            notes=(
                "31/10/2026 media library has 3744-Oct-31st-Nov-1st.pdf.",
                "Proved application/pdf, 558567 bytes. The filename has no single date the parser reads.",
                "wp-json uses the media date 30/10/2026. That is inside the week window. Do not pin the name.",
            ),
            do_not=(
                "Do not pin 3744-Oct-31st-Nov-1st.pdf.",
                "Do not take the older Oct 24th-25th JPEG while this PDF is in the library.",
            ),
            pattern_key="wp_json_weekend_range_pdf+direct_download",
        )

    if host == "booterstownparish.ie":
        return HubHint(
            key="booterstown_sunday_pdf",
            site_type="wp_json_newest_media",
            label="Booterstown Sun-D-Month-YYYY PDF in wp-json",
            confidence="high",
            notes=(
                "31/10/2026 local wp-json proved Sun-1-November-2026-Booterstown-Weekly-Newsletter.pdf (application/pdf, 01/11/2026) and Sun-25-October-2026-Booterstown-Weekly-Newsletter.pdf (25/10/2026).",
                "GitHub run 41227678445 guessed Newsletter-25th-October-2026-30th-Sunday-in-Ordinary-Time.pdf and missed. wp-json then scored nothing.",
                "The homepage HTML has no PDF link. Ask for Sun-D-Month-YYYY-Booterstown-Weekly-Newsletter.pdf before wp-json. Do not pin that name.",
                "Harvest 41244478540 asked for that exact Sun-25-October name. The browser said miss, then the parish timed out three times. Do not send it again.",
            ),
            do_not=(
                "Do not pin the dated filename.",
                "Do not harvest the front.png as the bulletin.",
                "Do not send the same wp-json-only harvest again.",
                "Do not send Booterstown again.",
            ),
            pattern_key="booterstown_sunday_pdf+direct_download",
        )

    if host == "borrisokaneparish.ie":
        return HubHint(
            key="homepage_pdf_when_wpjson_404",
            site_type="http_scrape_newest_pdf",
            label="Homepage PDF when wp-json media is 404",
            confidence="high",
            notes=(
                "31/10/2026 /wp-json/wp/v2/media returned HTTP 404.",
                "The homepage links 1st-Nov.-2026-newsletter.pdf. Proved application/pdf, 349130 bytes, date 01/11/2026.",
                "Scrape the homepage. Do not pin the filename.",
                "Harvest 41244475049 ok. Saved 1st-Nov.-2026-newsletter.pdf. Date 01/11/2026.",
            ),
            do_not=("Do not pin the dated filename.", "Do not keep calling wp-json when it returns 404."),
            pattern_key="homepage_pdf_when_wpjson_404+direct_download",
        )

    if host == "parishestogether.ie":
        return HubHint(
            key="prefix_ddmmyy_pdf",
            site_type="http_scrape_newest_pdf",
            label="Parishes Together prefix-DD-MM-YY.pdf",
            confidence="high",
            notes=(
                "31/10/2026 the newsletters list proved Carraig-25-10-26.pdf, Glanmire-25-10-26.pdf, Glounthaune-25-10-26.pdf, and Wgh-25-10-26.pdf.",
                "Each prefix is one parish. The date in the filename is DD-MM-YY. Do not pin it.",
                "Harvests ok on 25/10/2026: Carraig 41244089626, Glanmire 41244092792, Glounthaune 41244096765, Watergrasshill 41244100197.",
            ),
            do_not=(
                "Do not pin the dated filename.",
                "Do not scrape another parish prefix into this recipe.",
            ),
            pattern_key="prefix_ddmmyy_pdf+direct_download",
        )

    if host == "bantryfamilyofparishes.ie":
        return HubHint(
            key="bantry_family_pdf",
            site_type="http_scrape_newest_pdf",
            label="Bantry family weekly PDF, harvest once",
            confidence="high",
            notes=(
                "One weekly PDF covers Bantry, Caheragh, Goleen, Muintir Bhaire, and Schull.",
                "31/10/2026 proved 25th_October_2026.2.pdf (25/10/2026) and 1st_November_2026.pdf.",
                "Harvest once under bantry. The .2 is a site suffix. This Sunday's file wins when both are listed.",
            ),
            do_not=(
                "Do not pin the dated filename.",
                "Do not add recipes for caheragh, goleen, muintirbhaire, or schull.",
            ),
            pattern_key="bantry_family_pdf+direct_download",
        )

    if host == "castleconnellparish.ie":
        return HubHint(
            key="spelled_month_listing_pdf",
            site_type="http_scrape_newest_pdf",
            label="Castleconnell Newsletter-Dth-Month-YYYY.pdf",
            confidence="high",
            notes=(
                "31/10/2026 /newsletter/ proved Newsletter-25th-October-2026.pdf (application/pdf, 205363 bytes).",
                "A 1 November file on the same page is a Word document. Keep the PDF.",
                "Harvest 41244083938 ok. Saved Newsletter-25th-October-2026.pdf. Date 25/10/2026.",
            ),
            do_not=("Do not pin the dated filename.", "Do not save the Word file as the bulletin."),
            pattern_key="spelled_month_listing_pdf+direct_download",
        )

    if host == "churchtownparish.com":
        return HubHint(
            key="iso_newsletter_pdf",
            site_type="http_scrape_newest_pdf",
            label="Churchtown newsletter-YYYY-MM-DD.pdf",
            confidence="high",
            notes=(
                "31/10/2026 /newsletter/ proved newsletter-2026-11-01.pdf (application/pdf, 1400380 bytes).",
                "This Sunday was not on the page. The 01/11/2026 file is inside the 8-day window.",
                "Harvest 41244086775 timed out three times. The file was proved locally. Do not send the same scrape again.",
            ),
            do_not=("Do not pin the dated filename.",),
            pattern_key="iso_newsletter_pdf+direct_download",
        )

    if host == "clarecastleballyeaparish.ie":
        return HubHint(
            key="spelled_month_listing_pdf",
            site_type="http_scrape_newest_pdf",
            label="Clarecastle Dth-Month-YYYY.pdf",
            confidence="high",
            notes=(
                "31/10/2026 /newsletter/ proved 25th-October-2026.pdf (application/pdf, 234789 bytes) and 1st-November-2026.pdf.",
                "This Sunday's PDF wins. Harvest 41248893099 is sent. Not ok until that run says so.",
            ),
            do_not=("Do not pin the dated filename.", "Do not take the community lotto page."),
            pattern_key="spelled_month_listing_pdf+direct_download",
        )

    if host == "imeallboirne.ie":
        return HubHint(
            key="spelled_month_listing_pdf",
            site_type="http_scrape_newest_pdf",
            label="Corofin Dth-Month-YYYY Newsletter PDF",
            confidence="high",
            notes=(
                "31/10/2026 /newsletter/ proved 25th-October-2026-Newsletter.pdf (application/pdf, 311256 bytes) and 1st-November-2026-Newsletter-1.pdf.",
                "This Sunday's PDF wins. Harvest 41248896002 is sent. Not ok until that run says so.",
            ),
            do_not=("Do not pin the dated filename.",),
            pattern_key="spelled_month_listing_pdf+direct_download",
        )

    if host == "saintabbans.com":
        return HubHint(
            key="html_listing_still_stale",
            site_type="html_text_bulletin",
            label="Adamstown HTML listing, still 18 October",
            confidence="high",
            notes=(
                "31/10/2026 http://saintabbans.com/?page_id=21 top post is still 18th October 2026.",
                "No PDF on that listing. Leave the parish stale.",
            ),
            do_not=("Do not pin ?p=1605.",),
            pattern_key="html_listing_still_stale+direct_download",
        )

    if path.rstrip("/").endswith("current-newsletter"):
        return HubHint(
            key="current_newsletter_redirect",
            site_type="permanent_redirect_document",
            label="Permanent /current-newsletter/ path (Kildare / Naas / Bellaghy pattern)",
            confidence="high",
            notes=(
                "Same URL every week. It redirects to this Sunday's PDF. Do not pin the dated upload.",
                "28/10/2026 Bellaghy: when the redirect is last week, leave it stale. "
                "Homepage rescrape pulled a pope-francis jpeg and marked the parish failed.",
                "Always set disable_stale_rescrape_fallback on these recipes.",
            ),
            do_not=(
                "Do not pin the dated wp-content filename.",
                "Do not rescrape the homepage when /current-newsletter/ is stale.",
                "Do not download pope-francis, Irish-Bishops, Gaza appeal, or GDPR PDFs from the homepage.",
            ),
            pattern_key="current-newsletter+direct_download",
        )

    if "wp-json" in path or path.rstrip("/").endswith("newsletters"):
        return HubHint(
            key="wp_json_media",
            site_type="wp_json_newest_media",
            label="WordPress media library (Ashbourne / Askea pattern)",
            confidence="high",
            notes=(
                "Ashbourne: listing had no calendar date in the PDF href. wp-json scored the file.",
                "Askea: /newsletters/ lists dated PDFs. Do not pin the dated name.",
                "31/10/2026 urllib GET of ashbourneparish.ie/newsletters/ returned HTTP 403. That is not proof the file is missing. Use the browser or wp-json.",
            ),
            do_not=("Do not pin a dated filename.", "Do not harvest Facebook."),
            pattern_key="wp_json+direct_download",
        )

    if "/wp-content/uploads/" in path and path.endswith(".pdf"):
        return HubHint(
            key="forbidden_page_browser_pdf",
            site_type="wp_json_newest_media",
            label="Sunday upload. A 403 page means use the browser (Cloyne)",
            confidence="high",
            notes=(
                "Cloyne 24/10/2026. urllib gets a page titled 403 - Forbidden. The browser GET of this Sunday's uploads name is the PDF.",
                "Another parish that answers with that same page is the same problem. Do not pin the dated filename.",
            ),
            do_not=(
                "Do not retry urllib until the parish time limit.",
                "Do not pin the dated filename.",
            ),
            pattern_key="forbidden_page+browser_pdf",
        )

    lower = raw.lower()
    if "/_files/ugd/" in path:
        return _step_hint(
            "wix_link_text_date",
            "wix_link_text_date",
            "Wix hash. The date is in the link text",
            "Irvinestown and Truagh. Do not save the /_files/ugd/ hash.",
            "Do not pin the Wix hash.",
        )
    if "onewebmedia/" in path and path.endswith(".pdf"):
        return _step_hint(
            "onewebmedia_pdf",
            "onewebmedia_pdf",
            "One.com onewebmedia PDF",
            "Lisnaskea and Galloon. An expired certificate is not a missing file.",
            "Do not pin the onewebmedia hash.",
        )
    if path.endswith(".rtf"):
        return _step_hint(
            "rtf_newsletter",
            "rtf_newsletter",
            "Weekly RTF",
            "Magheracloone. Take the newest .rtf.",
            "Do not invent a PDF name.",
        )
    if "/pdf/" in path and path.endswith(".pdf"):
        return _step_hint(
            "predicted_dated_pdf",
            "predicted_dated_pdf",
            "Dated /pdf/ file when the listing looks empty",
            "Tempo, Longford and Beragh. Prove the date from the file name.",
            "Do not pin the dated /pdf/ name.",
        )
    if "articledetail.aspx" in path:
        return _step_hint(
            "connect_news_article",
            "connect_news_article",
            "NEWS.aspx article titled Parish Newsletter",
            "The date is in the link text. Do not save the diocese /parishes/ page.",
            "Do not save a diocese profile page.",
        )
    if "fileid=" in lower or "/index.cfm/_api/render/file/" in lower:
        return _step_hint(
            "http_scrape_newest_pdf",
            "http_scrape_newest_pdf",
            "Hashed file link. The date is in the link text",
            "Mura fileID. Do not pin the hash. Score the link text.",
            "Do not pin a fileID.",
        )

    return None


def _step_hint(
    key: str,
    site_type: str,
    label: str,
    note: str,
    do_not: str,
) -> HubHint:
    """One stored step, used when a new URL looks like a parish already solved."""
    return HubHint(
        key=key,
        site_type=site_type,
        label=label,
        confidence="high",
        notes=(note,),
        do_not=(do_not, "Do not pin a dated filename."),
        pattern_key=key,
    )


def brain_steps() -> tuple[dict, ...]:
    """The proved steps. Hunt notes live in this list, not in a second copy."""
    from harvester.newsletter_brain import stored_steps

    return stored_steps()


def accepted_hunt_dates(today: date | None = None) -> set[date]:
    """This Sunday, last Sunday, and Fri–Mon around this Sunday."""
    sunday = target_sunday(today)
    prev = sunday - timedelta(days=7)
    days = {sunday, prev}
    for offset in (-2, -1, 0, 1):
        days.add(sunday + timedelta(days=offset))
    return days


def _blocked_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        bare = host[4:]
    else:
        bare = host
    return host in _SKIP_HOSTS or bare in _SKIP_HOSTS or host in _DIRECTORY_HOSTS or bare in _DIRECTORY_HOSTS


def load_skip_recipes(recipes_dir: Path | None = None) -> list[dict[str, Any]]:
    root = recipes_dir or RECIPES_DIR
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("skip") is not True:
            continue
        if data.get("alias_of"):
            continue
        data["_path"] = str(path)
        rows.append(data)
    return rows


def candidate_probe_urls(start_url: str) -> list[tuple[str, str, str]]:
    """Return (url, site_type, pattern_key) probes from remembered tricks.

    Does not invent Facebook or diocese-directory files.
    """
    raw = (start_url or "").strip()
    if not raw or _blocked_host(raw):
        return []
    parsed = urlparse(raw)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    hint = hint_for_url(raw)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(url: str, site_type: str, pattern_key: str) -> None:
        url = url.strip()
        if not url or url in seen or _blocked_host(url):
            return
        seen.add(url)
        out.append((url, site_type, pattern_key))

    if hint and hint.confidence == "high":
        add(raw, hint.site_type, hint.pattern_key or hint.key)

    if hint is None or hint.key != "churchservices_tv":
        add(
            origin.rstrip("/") + "/current-newsletter/",
            "permanent_redirect_document",
            "current-newsletter+direct_download",
        )
        add(
            origin.rstrip("/") + "/newsletters/",
            "http_scrape_newest_pdf",
            "wp_json+direct_download",
        )
        add(
            origin.rstrip("/") + "/wp-json/wp/v2/media?per_page=100",
            "wp_json_newest_media",
            "wp_json+direct_download",
        )
        sunday = target_sunday()
        for day in (sunday, sunday - timedelta(days=7)):
            for url, site_type, pattern_key in _sunday_guess_probes(origin, day):
                add(url, site_type, pattern_key)
    return out


def _sunday_guess_probes(origin: str, sunday: date) -> list[tuple[str, str, str]]:
    """This Sunday's usual filenames. The last hunt never asked for these.

    Cloyne is the Newsletter liturgical name. Crumlin is the ISO name.
    Longford is /pdf/DDMMYY.pdf. Homepage probes alone missed all three.
    """
    from harvester.newsletter_brain import filename_shapes

    root = origin.rstrip("/")
    picked: list[str] = []
    for name in filename_shapes(sunday):
        low = name.lower()
        if low.startswith("newsletter-") or low.endswith("-newsletter.pdf"):
            picked.append(name)
        elif (
            low.endswith(".pdf")
            and len(low) == 10
            and low[:6].isdigit()
            and low[6] == "."
        ):
            picked.append(name)
    names: list[str] = []
    for name in picked:
        if name not in names:
            names.append(name)
    names = names[:3]
    for name in filename_shapes(sunday):
        low = name.lower()
        if low.startswith("n") and low[1:2].isdigit() and low.endswith(".pdf") and name not in names:
            names.append(name)
            break
    folder = f"{root}/wp-content/uploads/{sunday.year}/{sunday.month:02d}/"
    found: list[tuple[str, str, str]] = []
    short = ""
    for name in names:
        found.append((folder + name, "wp_json_newest_media", "sunday_named_upload"))
        if len(name) == 10 and name[:6].isdigit() and name[6] == ".":
            short = name
    if short:
        found.append((f"{root}/pdf/{short}", "predicted_dated_pdf", "predicted_dated_pdf"))
    return found


def _http_get(url: str, timeout: int = 20) -> tuple[int, str, bytes, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read(256_000)
        ctype = resp.headers.get("Content-Type") or ""
        final = resp.geturl() or url
        return int(resp.status), ctype, body, final


def _magic_ok(body: bytes, ctype: str) -> str | None:
    lowered = (ctype or "").lower()
    if body.startswith(b"%PDF") or "application/pdf" in lowered:
        return "pdf"
    if body[:3] == b"\xff\xd8\xff" or "image/jpeg" in lowered or "image/jpg" in lowered:
        return "jpeg"
    return None


def _date_ok(text: str, accepted: set[date]) -> date | None:
    found = extract_date_from_string(text)
    if found in accepted:
        return found
    return None


def prove_this_week_file(url: str, accepted: set[date]) -> dict[str, Any] | None:
    """GET 200 + %PDF/JPEG + date on the URL. No invented dates."""
    try:
        status, ctype, body, final = _http_get(url)
    except Exception:
        return None
    if status != 200:
        return None
    kind = _magic_ok(body, ctype)
    if kind == "pdf" and body.startswith(b"%PDF") is False and "json" in ctype.lower():
        return _prove_from_wp_json(body, url, accepted)
    if kind == "pdf" or (kind is None and "html" in ctype.lower()):
        if kind == "pdf":
            found = _date_ok(final, accepted) or _date_ok(url, accepted)
            if found is None:
                return None
            return {
                "url": final,
                "kind": "pdf",
                "bytes": len(body),
                "date": found.isoformat(),
            }
        return _prove_from_listing_html(body, final, accepted)
    if kind == "jpeg":
        found = _date_ok(final, accepted) or _date_ok(url, accepted)
        if found is None:
            return None
        return {
            "url": final,
            "kind": "jpeg",
            "bytes": len(body),
            "date": found.isoformat(),
        }
    if "json" in ctype.lower() or urlparse(url).path.lower().find("wp-json") >= 0:
        return _prove_from_wp_json(body, url, accepted)
    return None


def _prove_from_listing_html(body: bytes, page_url: str, accepted: set[date]) -> dict[str, Any] | None:
    try:
        html = body.decode("utf-8", errors="ignore")
    except Exception:
        return None
    for href in _HREF_PDF_RE.findall(html):
        absolute = urljoin(page_url, href)
        found = _date_ok(absolute, accepted) or _date_ok(href, accepted)
        if found is None:
            continue
        try:
            status, ctype, blob, final = _http_get(absolute)
        except Exception:
            continue
        if status != 200 or _magic_ok(blob, ctype) != "pdf":
            continue
        if not blob.startswith(b"%PDF"):
            continue
        return {
            "url": final,
            "kind": "pdf",
            "bytes": len(blob),
            "date": found.isoformat(),
        }
    return None


def _prove_from_wp_json(body: bytes, page_url: str, accepted: set[date]) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    items = payload if isinstance(payload, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_url") or "")
        mime = str((item.get("mime_type") or "")).lower()
        if not source.lower().endswith(".pdf") and "pdf" not in mime:
            continue
        raw_title = item.get("title")
        if isinstance(raw_title, dict):
            title = str(raw_title.get("rendered") or "")
        else:
            title = str(raw_title or "")
        found = _date_ok(source, accepted) or _date_ok(title, accepted)
        if found is None:
            blob = f"{source} {title}".lower()
            if not any(word in blob for word in ("newsletter", "bulletin", "sunday")):
                continue
            raw_media = str(item.get("date") or "")[:10]
            try:
                media_day = date.fromisoformat(raw_media)
            except ValueError:
                continue
            if media_day not in accepted:
                continue
            found = media_day
        try:
            status, ctype, blob, final = _http_get(source)
        except Exception:
            continue
        if status != 200 or not blob.startswith(b"%PDF"):
            continue
        return {
            "url": final,
            "kind": "pdf",
            "bytes": len(blob),
            "date": found.isoformat(),
        }
    return None


def remember_win(
    pattern_key: str,
    parish_key: str,
    note: str,
    patterns_path: Path | None = None,
) -> None:
    """Write a proved trick into site_patterns.json (click memory)."""
    path = patterns_path or PATTERNS_PATH
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "description": "Learned site layout patterns.", "patterns": {}}
    patterns = data.setdefault("patterns", {})
    row = patterns.get(pattern_key)
    if not isinstance(row, dict):
        row = {
            "page_type": pattern_key.split("+")[0],
            "recipe_flow": "direct_download",
            "label": pattern_key,
            "advice": note,
            "operator_notes": [],
            "do_not": ["Do not pin a dated filename.", "Do not harvest Facebook."],
            "example_parishes": [],
            "success_count": 0,
        }
        patterns[pattern_key] = row
    examples = row.setdefault("example_parishes", [])
    if parish_key and parish_key not in examples:
        examples.append(parish_key)
    row["success_count"] = int(row.get("success_count") or 0) + 1
    notes = row.setdefault("operator_notes", [])
    if note and note not in notes:
        notes.append(note)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unskip_recipe(recipe: dict[str, Any], *, site_type: str, start_url: str, note: str) -> None:
    path = Path(recipe["_path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["skip"] = False
    data.pop("reason", None)
    if data.get("status") == "inactive":
        data["status"] = "active"
    data["site_type"] = site_type
    data["playbook_type"] = "direct_download"
    data["start_url"] = start_url
    data["recorded_date"] = date.today().isoformat()
    data["steps"] = [{"action": "goto", "url": start_url}]
    if site_type == "permanent_redirect_document":
        data["steps"] = [{"action": "download", "url": start_url, "use_target_url": True}]
        # Referee must not homepage-rescrape when the permanent file is last week
        # (Bellaghy 28/10/2026: pope-francis jpeg → false failed).
        data["disable_stale_rescrape_fallback"] = True
    notes = data.setdefault("operator_notes", [])
    notes.append(note)
    do_not = data.setdefault("do_not", [])
    for line in (
        "Do not pin a dated filename.",
        "Do not harvest Facebook.",
        "Do not rescrape the homepage when the permanent newsletter link is stale.",
    ):
        if line not in do_not:
            do_not.append(line)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def scan_skipped(
    *,
    recipes_dir: Path | None = None,
    patterns_path: Path | None = None,
    cursor_path: Path | None = None,
    limit: int = 25,
    apply: bool = False,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Probe skipped recipes with remembered hub tricks. Optionally unskip."""
    skips = load_skip_recipes(recipes_dir)
    cursor_file = cursor_path or CURSOR_PATH
    offset = 0
    if cursor_file.exists():
        try:
            offset = int(json.loads(cursor_file.read_text(encoding="utf-8")).get("offset") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            offset = 0
    if skips:
        offset = offset % len(skips)
    window = skips[offset : offset + limit]
    if len(window) < limit:
        window.extend(skips[: max(0, limit - len(window))])
    accepted = accepted_hunt_dates(today)
    wins: list[dict[str, Any]] = []
    for recipe in window:
        start = str(recipe.get("start_url") or "")
        key = str(recipe.get("parish_key") or Path(recipe["_path"]).stem)
        for url, site_type, pattern_key in candidate_probe_urls(start):
            proved = prove_this_week_file(url, accepted)
            if not proved:
                continue
            listing_url = url
            if site_type == "permanent_redirect_document" and "/current-newsletter" in urlparse(url).path.lower():
                listing_url = url
            elif site_type == "wp_json_newest_media":
                listing_url = start or url
            elif site_type == "http_scrape_newest_pdf":
                listing_url = url
            uk = format_uk_date(proved["date"])
            note = (
                f"{format_uk_date(date.today())} Recipe Brain hub scan: proved GET 200 "
                f"{proved['kind']} {proved.get('bytes')} bytes dated {uk}. "
                f"Do not pin {proved['url']}."
            )
            win = {
                "parish_key": key,
                "site_type": site_type,
                "pattern_key": pattern_key,
                "start_url": listing_url,
                "proved_url": proved["url"],
                "date": proved["date"],
            }
            wins.append(win)
            if apply:
                _unskip_recipe(
                    recipe,
                    site_type=site_type,
                    start_url=listing_url
                    if site_type != "wp_json_newest_media"
                    else (start or listing_url),
                    note=note,
                )
                remember_win(pattern_key, key, note, patterns_path=patterns_path)
            break
    next_offset = offset + limit
    cursor_file.write_text(json.dumps({"offset": next_offset}, indent=2) + "\n", encoding="utf-8")
    return wins
