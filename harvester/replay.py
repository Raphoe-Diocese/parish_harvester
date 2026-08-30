from __future__ import annotations

import asyncio
import base64
import fnmatch
import io
import json
import re
import socket
import ssl
import subprocess
import tempfile
import time
from datetime import date, timedelta
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import HTTPHandler, HTTPSHandler, Request, build_opener, urlopen

from playwright.async_api import (
    Browser,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from PyPDF2 import PdfReader

from .cloud_folders import (
    is_cloud_folder_click_step,
    is_year_folder_click_step,
    newest_yy_mm_dd_label,
    rewrite_cloud_folder_click_step,
    rewrite_year_folder_click_step,
)
from .cloud_urls import (
    gdrive_confirm_token,
    gdrive_confirm_uuid,
    gdrive_download_url_with_confirm,
    is_cloud_document_url,
    normalize_document_url,
    unwrap_docs_viewer_url,
)
from .config import MAX_BULLETIN_PAGES, PAGE_LOAD_TIMEOUT_MS, PARISHES_DIR
from .liturgical import liturgical_date_from_text, year_hint_from_upload_url
from .utils import (
    _is_within_opaque_hash,
    _opaque_hash_spans,
    dropfiles_task_download_url,
    extract_date_from_slug,
    extract_date_from_string,
    churchmedia_channel_about_url,
    churchmedia_newsletter_url_from_about,
    churchmedia_slug_from_url,
    extract_mcn_church_id,
    extract_newsletter_number,
    looks_like_permanent_bulletin_url,
    mcn_newsletter_url_from_profile,
    mcn_profile_data_url,
    oneweb_newsletter_download_urls,
    parish_uploader_bulletin_candidates,
    predict_dropfiles_bulletin_urls,
    predicted_dated_upload_urls,
    predicted_wordpress_dated_post_urls,
    quote_http_url,
    rewrite_date_url,
    rewrite_newsletter_number_for_target,
    wix_dated_slug_candidates,
    yearless_slug_date,
)


class RecipeReplayError(RuntimeError):
    """Raised when replaying a trained parish recipe fails."""


DOCX_CONVERSION_TIMEOUT_S = 60
RECIPE_STEP_TIMEOUT_MS = PAGE_LOAD_TIMEOUT_MS
POST_CLICK_WAIT_TIMEOUT_MS = 3_000
# Extra grace period to wait for a native download event after a click when
# none has arrived yet. _click_locator_match's own settle window
# (POST_CLICK_WAIT_TIMEOUT_MS) is tuned for navigation, but some servers are
# slow enough (~2.5-3s observed) that the download event fires just *after*
# that window closes — the download was genuinely in flight, not missing.
# Without this, replay falls through to fallback discovery chains that don't
# apply to the recipe and eventually times out (found 2026-08-09,
# parishoflisburn).
DELAYED_DOWNLOAD_WAIT_MS = 10_000
MAX_SELECTOR_ERRORS = 3
DROPFILES_DOWNLOAD_SELECTORS = (
    ".mod_dropfiles_latest a.mod_downloadlink[href]",
    ".mod_dropfiles_list a.mod_downloadlink[href]",
    "a.mod_downloadlink[href]",
)
_DROPFILES_FILE_ID_RE = re.compile(
    r"/(?:Newsletters|Weekly-Bulletins|Bulletins)/(\d+)/",
    re.IGNORECASE,
)
# Matches a Joomla Dropfiles download anchor regardless of whether the
# mod_downloadlink class appears before or after the href attribute in the
# raw HTML (both orders seen in the wild).
_MOD_DOWNLOADLINK_HREF_RE = re.compile(
    r'<a\b[^>]*?(?:\bmod_downloadlink\b[^>]*?\bhref="([^"]+)"'
    r'|\bhref="([^"]+)"[^>]*?\bmod_downloadlink\b)',
    re.IGNORECASE,
)
# threepatrons.org / stmarysportglenone.org (both Joomla Dropfiles on the same
# SiteGround-hosted infra) front their whole origin with an "sg-captcha"
# challenge that is PROBABILISTIC, not deterministic — plain HTTP requests
# (curl/urllib) got through with a real 200 + file roughly 1 attempt in 5-10
# in manual testing (found 2026-08-10), while a full Playwright headless
# browser navigation to the exact same URL failed 0/20 times in a row. The
# browser's TLS/JS fingerprint appears to be flagged far more consistently
# than a bare urllib request, so retrying via page.goto (the old approach)
# almost never worked even though the underlying file was never actually
# unreachable. Retrying a plain HTTP GET a couple of dozen times is fast
# (~0.3-1.5s per attempt) and far more reliable for this specific WAF.
_DROPFILES_HTTP_ATTEMPTS = 60
_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S = 5.0
_DROPFILES_HTTP_LISTING_BUDGET_S = 45.0
_DROPFILES_HTTP_FILE_BUDGET_S = 45.0
_DROPFILES_HTTP_PREDICTED_BUDGET_S = 20.0
_DROPFILES_HTTP_OVERALL_BUDGET_S = 100.0
# waf_retry_wordpress needs a bigger shared budget than the dropfiles path:
# it can require up to 3 sequential HTTP-retry stages (listing -> post ->
# file, sometimes several files for a multi-page image bulletin) against the
# same probabilistic sg-captcha challenge, each of which may need its own
# handful of retries. Must stay comfortably under a recipe's total_timeout_s
# (190s for these recipes) including the ~5s safety margin per stage.
_WAF_RETRY_OVERALL_BUDGET_S = 160.0
PDFEMB_SELECTOR = "a.pdfemb-viewer[href]"
PDFEMB_HREF_EXTRACT_JS = "(els) => els.map(el => el.getAttribute('href')).filter(Boolean)"

_ALWAYS_NON_BULLETIN_RE = re.compile(
    r"gdpr|\bprivacy\b|privacy[-_\s]?policy|wedding[-_\s]?parish|\bwedding\b|"
    r"order[-_\s]?of[-_\s]?mass|giftaid|gift[-_\s]?aid|"
    r"financial[-_\s]?statement|income[-_\s]?(?:&|and)?[-_\s]?expenditure|"
    r"dataentry|data[-_\s]?entry|new[-_\s]?parishioner|parishioner[-_\s]?form",
    re.IGNORECASE,
)
_NON_BULLETIN_RE = re.compile(
    r"dataentry|giftaid|standingorder|donation|prayer|safeguarding|privacy|gdpr|diocese|"
    r"sitemap|application|registration|volunteer|finances|financial|parishdraw|mcn\s*media|"
    r"gaza|bishops-call|bishops?[-_]?letter|pastoral[-_]?letter|draw_poster|poster_20\d{2}|"
    r"order[-_]?of[-_]?mass|catholicbishops\.ie|wedding[-_]?parish|"
    r"fbcdn\.net|facebook\.com",
    re.IGNORECASE,
)
_BULLETIN_KEYWORD_RE = re.compile(r"\b(bulletin|newsletter)\b", re.IGNORECASE)
_D_M_YY_IN_URL_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)")
# Dot-separated DD.MM.YY (UK convention) — e.g. stbrigidsparishbelfast.org's
# "Parish-Bulletin-09.08.26-FOR-PRINTING.pdf". harvester.utils.extract_date_from_string
# treats this same N.N.NN dot shape as YY.MM.DD (needed for Google Drive folder-row
# dates and locked in by tests/test_cloud_folders.py), which silently misreads UK
# DD.MM.YY filenames — "09.08.26" as YY.MM.DD is 2009-08-26, so it always lost to an
# older bulletin whose digits happened to parse as a more "recent-looking" fake
# YY.MM.DD year (found live: 26.07.26 beat 09.08.26 because misread as 2026-07-26).
# Score both interpretations and let max() pick whichever is more plausible.
_D_M_YY_DOT_IN_URL_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)")
# WordPress media folders (/wp-content/uploads/YYYY/MM/) are authoritative for the
# *upload* month even when the filename itself carries no date at all (e.g. a slug
# named after the liturgical feast: "Sixteenth-Sunday-of-Ordinary-Time.pdf"). Used
# as a score floor so a recent undated bulletin still outranks an old but
# explicitly-dated one from a prior year (see glenariffeparish 2026-08-09 fix).
# WordPress and Kirby/custom parish CMS folders. kincasslagh.ie uses
# /app/uploads/YYYY/MM/ not /wp-content/uploads/ — without that, an
# undated Newsletter-21st-Aug.pdf scored 0 and lost to 20260705.pdf
# (found 2026-08-23).
_WP_UPLOADS_YEAR_MONTH_RE = re.compile(
    r"/(?:wp-content/|app/)?uploads/(20\d{2})/(0?[1-9]|1[0-2])/",
    re.IGNORECASE,
)


def _is_non_bulletin_url(url: str) -> bool:
    text = unquote(url or "")
    if _ALWAYS_NON_BULLETIN_RE.search(text):
        return True
    if _BULLETIN_KEYWORD_RE.search(text):
        return False
    return bool(_NON_BULLETIN_RE.search(text))


def _normalized_href_patterns(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(p).strip().lower() for p in values if str(p).strip()]


def _click_href_filters(step: dict, recipe: dict | None) -> tuple[list[str], list[str]]:
    recipe = recipe or {}
    patterns = _normalized_href_patterns(recipe.get("href_patterns"))
    patterns.extend(_normalized_href_patterns(step.get("href_patterns")))
    skips = _normalized_href_patterns(recipe.get("href_skip_patterns"))
    skips.extend(_normalized_href_patterns(step.get("href_skip_patterns")))
    return patterns, skips


def _href_is_skipped(url: str, skip_patterns: list[str]) -> bool:
    if not skip_patterns:
        return False
    blob = _href_match_blob(url)
    return any(pat.replace(" ", "-") in blob or pat in blob for pat in skip_patterns)


def _href_allowed_for_click(
    url: str,
    href_patterns: list[str] | None = None,
    href_skip: list[str] | None = None,
) -> bool:
    if _is_non_bulletin_url(url):
        return False
    if _href_is_skipped(url, href_skip or []):
        return False
    if href_patterns and not _href_matches_patterns(url, href_patterns):
        return False
    return True


def _looks_like_http_url(url: str) -> bool:
    return (url or "").strip().lower().startswith(("http://", "https://"))


def _looks_like_direct_document_url(url: str) -> bool:
    lower = unquote((url or "").strip()).lower()
    if not _looks_like_http_url(lower):
        return False
    if "drive.usercontent.google.com/download" in lower:
        return True
    if looks_like_permanent_bulletin_url(url):
        return True
    path = urlparse(lower).path
    return path.endswith((".pdf", ".docx", ".doc")) or "/pdf/" in path


def _is_gdrive_usercontent_url(url: str) -> bool:
    return "drive.usercontent.google.com/download" in unquote((url or "").strip()).lower()


def _recipe_is_gdrive_static(recipe: dict) -> bool:
    if str(recipe.get("site_type") or "").strip().lower() == "google_drive_static":
        return True
    if _is_gdrive_usercontent_url(str(recipe.get("start_url") or "")):
        return True
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip().lower() != "download":
            continue
        if _is_gdrive_usercontent_url(str(step.get("url") or "")):
            return True
    return False


def _gdrive_download_url_from_recipe(recipe: dict) -> str:
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip().lower() == "download":
            url = str(step.get("url") or "").strip()
            if url:
                return normalize_document_url(url)
    start = str(recipe.get("start_url") or "").strip()
    return normalize_document_url(start) if start else ""


async def _goto_or_download(
    page: Page,
    dest: Path,
    url: str,
    downloads: list,
    timeout_ms: int,
    *,
    wait_until: str = "domcontentloaded",
) -> tuple[Path, str, str] | None:
    """Navigate or fetch a direct document URL (Drive downloads abort normal goto)."""
    if _looks_like_direct_document_url(url):
        # HTTP first — Drive usercontent URLs abort Playwright goto with ERR_ABORTED.
        # Parish Press Uploader parishes may have swapped this week's file to a
        # different extension (docx/jpg/...); try every candidate here so the
        # goto step succeeds directly instead of falling through to a slower
        # browser-nav fallback and then the recipe's separate download step.
        for candidate in parish_uploader_bulletin_candidates(url) or [url]:
            tried = await _try_download_page_url(page, dest, candidate, timeout_ms=timeout_ms)
            if tried:
                return dest, tried[1], tried[0]
        if not _is_gdrive_usercontent_url(url):
            tried = await _try_browser_nav_download(page, dest, url, timeout_ms)
            if tried:
                return dest, tried[1], tried[0]
        return None
    try:
        await _navigate_page(page, url, timeout_ms, wait_until=wait_until)
    except PlaywrightError as exc:
        if "ERR_ABORTED" not in str(exc):
            raise
        # Chromium aborts goto() when the target is a redirect straight to a
        # file download (e.g. a "Current Newsletter" page that 302s to that
        # week's PDF) — the download itself already fired and landed in
        # *downloads* via the page-level listener set up in replay_recipe,
        # same as the existing click-step ERR_ABORTED handling (see
        # _click_locator_match). Without this, any goto step pointed at such
        # a redirect-to-download URL was misreported as "recipe replay
        # failed" even though the file downloaded successfully (found
        # 2026-08-10, bellaghyparish: /current-newsletter/ redirects straight
        # to that week's uploads/.../DD-Month-YYYY.pdf).
    return await _capture_document_after_navigation(page, dest, url, downloads, timeout_ms)


async def _capture_document_after_navigation(
    page: Page,
    dest: Path,
    nav_url: str,
    downloads: list,
    timeout_ms: int,
) -> tuple[Path, str, str] | None:
    if downloads:
        download = downloads.pop(0)
        file_type = await _save_download_to_pdf(download, dest)
        source_url = _download_source_url(download, page)
        return dest, file_type, source_url if source_url != page.url else (nav_url or page.url)
    if nav_url and _looks_like_direct_document_url(nav_url):
        tried = await _try_download_page_url(page, dest, nav_url, timeout_ms=timeout_ms)
        if tried:
            return dest, tried[1], tried[0]
    if _looks_like_http_url(page.url) and _is_document_url(page.url):
        source_url, file_type = await _download_document_url(
            page, page.url, dest, timeout_ms=timeout_ms
        )
        return dest, file_type, source_url
    return None


def _score_bulletin_url(url: str) -> tuple[int, int]:
    """Higher = better. (date_score, keyword_bonus)."""
    text = unquote(url or "").lower()
    keyword_bonus = 10 if _BULLETIN_KEYWORD_RE.search(text) else 0
    date_score = 0
    hash_spans = _opaque_hash_spans(text)
    for match in _D_M_YY_IN_URL_RE.finditer(text):
        if _is_within_opaque_hash(hash_spans, match.start(), match.end()):
            continue
        try:
            day, month, year = int(match.group(1)), int(match.group(2)), 2000 + int(match.group(3))
            date(year, month, day)  # validate before scoring — see UUID note below
            date_score = max(date_score, year * 10000 + month * 100 + day)
        except ValueError:
            continue
    for match in _D_M_YY_DOT_IN_URL_RE.finditer(text):
        if _is_within_opaque_hash(hash_spans, match.start(), match.end()):
            continue
        try:
            day, month, year = int(match.group(1)), int(match.group(2)), 2000 + int(match.group(3))
            date(year, month, day)
            date_score = max(date_score, year * 10000 + month * 100 + day)
        except ValueError:
            continue
    # BUG (found 2026-08-09, saintmichaelthearchangel): a GoDaddy/wsimg CDN
    # UUID path segment like ".../108951e4-fc38-.../Parish-Bulletin-31st..."
    # isn't caught by _opaque_hash_spans (each dash-separated UUID group is
    # <16 hex chars, below the "long opaque hash" threshold), so "108951"
    # inside "108951e4" matched this 6-digit DDMMYY probe as day=10 month=89
    # year=2051 — an *unvalidated* month=89 still produced a huge bogus score
    # (20518910) that beat every real, correctly-dated candidate on the page.
    # Constructing a real date() (below) rejects invalid month/day combos
    # regardless of whether the hash-span guard catches the token.
    for m in re.finditer(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", text):
        if _is_within_opaque_hash(hash_spans, m.start(), m.end()):
            continue
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
            date(year, month, day)
            date_score = max(date_score, year * 10000 + month * 100 + day)
        except ValueError:
            continue
    parsed = extract_date_from_string(text)
    if parsed:
        date_score = max(date_score, parsed.year * 10000 + parsed.month * 100 + parsed.day)
    today = date.today()
    yearless = yearless_slug_date(text, today.year, near=today)
    if yearless:
        date_score = max(
            date_score, yearless.year * 10000 + yearless.month * 100 + yearless.day
        )
    liturgical = liturgical_date_from_text(
        text, year_hint_from_upload_url(text, today.year)
    )
    if liturgical:
        date_score = max(
            date_score,
            liturgical.year * 10000 + liturgical.month * 100 + liturgical.day,
        )
    # Floor: an undated slug still belongs to its upload month (WordPress
    # /uploads/YYYY/MM/ folder), so it should outrank an older bulletin that
    # merely happens to have an explicit (but stale) date in its filename.
    wp_folder = _WP_UPLOADS_YEAR_MONTH_RE.search(text)
    if wp_folder:
        try:
            folder_score = int(wp_folder.group(1)) * 10000 + int(wp_folder.group(2)) * 100 + 1
            date_score = max(date_score, folder_score)
        except ValueError:
            pass
    return date_score, keyword_bonus


def _score_bulletin_link(href: str, label: str = "") -> tuple[int, int, int]:
    """Return (total_score, date_score, dom_tiebreak) for ranking bulletin links."""
    combined = f"{unquote(href or '')} {label or ''}"
    date_score, keyword_bonus = _score_bulletin_url(combined)
    notice_bonus = 5 if re.search(r"\b(notice|parish news|latest bulletin)\b", combined, re.I) else 0
    total = date_score * 100 + keyword_bonus + notice_bonus
    return total, date_score, keyword_bonus


def _url_matches_pattern(url: str, pattern: str) -> bool:
    lower = unquote(url).lower()
    pat = (pattern or "*.pdf").strip().lower() or "*.pdf"
    if fnmatch.fnmatch(lower, pat):
        return True
    if pat == "*.pdf":
        return ".pdf" in lower or "mdocs-file=" in lower
    if pat == "*.docx":
        return ".docx" in lower
    return False


def _pattern_prefers_docx(pattern: str) -> bool:
    pat = (pattern or "").strip().lower()
    return ".docx" in pat or pat.endswith("docx")


async def _collect_document_candidates(page: Page, pattern: str) -> list[str]:
    """Unwrap viewer URLs, drop admin docs, prefer newest newsletter."""
    pdfemb_links = await page.eval_on_selector_all(PDFEMB_SELECTOR, PDFEMB_HREF_EXTRACT_JS)
    raw_links = await page.eval_on_selector_all(
        "a[href],iframe[src],embed[src],object[data]",
        """
        (els) => els.map(el => el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data') || '').filter(Boolean)
        """,
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in [*pdfemb_links, *raw_links]:
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = unwrap_docs_viewer_url(urljoin(page.url, raw.strip()))
        if not _url_matches_pattern(resolved, pattern):
            continue
        if _is_non_bulletin_url(resolved):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    candidates.sort(
        key=lambda u: (_score_bulletin_url(u)[0], _score_bulletin_url(u)[1]),
        reverse=True,
    )
    return candidates


def _recipe_start_url(recipe: dict) -> str:
    """Recipe start URL — fall back to first goto step when start_url omitted."""
    start = (recipe.get("start_url") or "").strip()
    if start:
        return start
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip().lower() == "goto":
            url = (step.get("url") or "").strip()
            if url:
                return url
    return ""


def _recipe_step_timeout_ms(recipe: dict) -> int:
    """Per-step Playwright timeout — recipe value merged with host_profiles.json."""
    raw = recipe.get("timeout_ms", recipe.get("timeout"))
    try:
        if raw is None:
            base = RECIPE_STEP_TIMEOUT_MS
        else:
            base = min(max(int(raw), 1_000), 180_000)
    except (TypeError, ValueError):
        base = RECIPE_STEP_TIMEOUT_MS

    host_ms = int(
        _host_profile_for_start_url(_recipe_start_url(recipe)).get("navigation_timeout_ms") or 0
    )
    if host_ms > 0:
        base = max(base, host_ms)
    return base


_VALID_NAV_WAIT_UNTIL = frozenset({"commit", "domcontentloaded", "load", "networkidle"})
_HOST_PROFILES_RAW: dict | None = None


def _load_host_profiles_raw() -> dict:
    global _HOST_PROFILES_RAW
    if _HOST_PROFILES_RAW is not None:
        return _HOST_PROFILES_RAW
    fallback: dict = {"_default": {}, "hosts": {}}
    profiles_path = PARISHES_DIR / "host_profiles.json"
    try:
        loaded = json.loads(profiles_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            if isinstance(loaded.get("_default"), dict):
                fallback["_default"] = loaded["_default"]
            if isinstance(loaded.get("hosts"), dict):
                fallback["hosts"] = loaded["hosts"]
    except Exception:
        pass
    _HOST_PROFILES_RAW = fallback
    return fallback


def _host_profile_for_start_url(start_url: str) -> dict:
    profiles = _load_host_profiles_raw()
    merged = dict(profiles.get("_default", {}))
    host = urlparse(start_url).netloc.lower().split(":", 1)[0]
    candidates = [host]
    if host.startswith("www."):
        candidates.append(host[4:])
    elif host:
        candidates.append(f"www.{host}")
    hosts = profiles.get("hosts", {})
    if isinstance(hosts, dict):
        for key in candidates:
            override = hosts.get(key)
            if isinstance(override, dict):
                merged.update(override)
                break
    return merged


def _recipe_navigation_wait_until(recipe: dict) -> str:
    """How eagerly goto waits — slow WordPress hosts often need ``commit``."""
    raw = str(recipe.get("navigation_wait_until") or "").strip().lower()
    if raw in _VALID_NAV_WAIT_UNTIL:
        return raw
    host_wait = str(
        _host_profile_for_start_url(_recipe_start_url(recipe)).get("navigation_wait_until") or ""
    ).strip().lower()
    if host_wait in _VALID_NAV_WAIT_UNTIL:
        return host_wait
    return "domcontentloaded"


_MDOCS_FILE_ID_RE = re.compile(r"[?&]mdocs-file=(\d+)", re.I)
_MDOCS_TABLE_ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.I | re.S)
_MDOCS_DOWNLOAD_HREF_RE = re.compile(
    r"""(?:href|data-download)=["']([^"']*mdocs-file=\d+[^"']*)["']""",
    re.I,
)


def _mdocs_file_id(url: str) -> int:
    match = _MDOCS_FILE_ID_RE.search(url or "")
    return int(match.group(1)) if match else 0


async def _find_mdocs_pdf_urls(page: Page) -> list[str]:
    """mDocs plugin lists — latest bulletin is first row (site copy)."""
    raw_links = await page.eval_on_selector_all(
        "table.mdocs a[href], table#mdocs-list-table a[href], "
        "a.mdocs-download[href], a[href*='mdocs-file'], "
        ".mdocs a[href], .mdocs-file a[href]",
        "(els) => els.map(el => el.getAttribute('href') || '').filter(Boolean)",
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in raw_links:
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = urljoin(page.url, raw.strip())
        lower = resolved.lower()
        if ".pdf" not in lower and "mdocs-file=" not in lower:
            continue
        if _is_non_bulletin_url(resolved):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    candidates.sort(
        key=lambda u: (
            _score_bulletin_url(u)[0],
            _score_bulletin_url(u)[1],
            _mdocs_file_id(u),
        ),
        reverse=True,
    )
    return candidates


async def _wait_for_bulletin_content(page: Page, recipe: dict, timeout_ms: int) -> None:
    """Slow hosts: wait for mdocs table, wp-block-file embed, or pdfemb links after commit navigation."""
    playbook = str(recipe.get("playbook_type") or recipe.get("site_type") or "").lower()
    probes: list[str] = []
    pdfemb_site = "pdfemb" in playbook or "wp_pdfemb" in playbook
    if pdfemb_site:
        # Newer PDF Embedder paints canvases and fetches PDFs over the network —
        # often with NO a.pdfemb-viewer[href]. Prefer canvas, then poll network PDFs.
        probes.extend(
            [
                "canvas.pdfemb-viewer",
                "div.pdfemb-viewer canvas",
                "a.pdfemb-viewer[href]",
                'a[class*="pdfemb"][href*=".pdf"]',
            ]
        )
    if "mdocs" in playbook:
        probes.extend(
            [
                "table.mdocs",
                "table#mdocs-list-table",
                "a.mdocs-download",
                "a[href*='mdocs-file']",
                ".mdocs a[href]",
            ]
        )
    if "wp_block" in playbook or "permanent_bulletin" in playbook:
        probes.extend(["object.wp-block-file__embed", ".wp-block-file a[href$='.pdf']"])
    if "mcn_live" in playbook or "mcn_pdf" in playbook:
        probes.extend(
            [
                "a[href$='.pdf']",
                "a[href*='.pdf']",
                "a[href*='bulletin']",
                "a[href*='download']",
            ]
        )
    if "churchmedia" in playbook:
        probes.extend(
            [
                "a[href*='/newsletter/'][href*='.pdf']",
                "a[href*='churchmedia.tv/newsletter/']",
            ]
        )
    if not probes:
        probes = [
            "a.pdfemb-viewer[href]",
            "table.mdocs",
            "object.wp-block-file__embed",
            "a[href$='.pdf']",
        ]
    budget = min(max(int(timeout_ms), 15_000), 240_000)
    if pdfemb_site:
        per_sel = min(8_000, max(3_000, budget // max(len(probes), 1)))
        for sel in probes:
            try:
                await page.wait_for_selector(sel, timeout=per_sel)
                break
            except PlaywrightTimeoutError:
                continue
        deadline = asyncio.get_event_loop().time() + min(budget / 1000, 25)
        while asyncio.get_event_loop().time() < deadline:
            try:
                found = await page.evaluate(
                    """() => performance.getEntriesByType('resource')
                        .some(r => /\\.pdf($|\\?)/i.test(r.name))"""
                )
            except Exception:
                found = False
            if found:
                return
            await asyncio.sleep(0.5)
        return
    # BUG (found 2026-08-09): this used to give EACH probe the full `budget`
    # timeout, so a recipe with no site_type/playbook_type (falls through to
    # the 4-selector default list above) could burn 4x the per-step timeout
    # just on this one wait — e.g. 4x40s=160s — before ever reaching the
    # click/download steps. That alone accounted for most of the "Total
    # timeout exceeded" failures across a whole diocese (Down & Connor:
    # drumquinparish, carrickparish, holy-familyparish, saintannesparish,
    # glenariffeparish, and ~15 more all share this exact recipe shape).
    #
    # BUG 2 (found 2026-08-09, later same day): dividing the budget still
    # checked probes ONE AT A TIME in sequence, so a slow-rendering site
    # (e.g. holyrosaryparishbelfast's Wix page) burned the full divided
    # timeout on each of the 3 probes that never match (pdfemb/mdocs/
    # wp-block markup this site doesn't use) before finally reaching the
    # 4th ("a[href$='.pdf']") — which the download step's own instant DOM
    # query finds immediately once the page has actually finished
    # rendering. Waiting on all probes AT ONCE (comma-joined CSS selector,
    # matches if ANY of them appears) returns as soon as the real content
    # shows up instead of wasting time walking irrelevant probes first.
    try:
        await page.wait_for_selector(", ".join(probes), timeout=budget)
        return
    except PlaywrightTimeoutError:
        pass
    try:
        wait_after = int(
            _host_profile_for_start_url(recipe.get("start_url") or page.url).get(
                "wait_after_load_ms"
            )
            or 0
        )
    except (TypeError, ValueError):
        wait_after = 0
    if wait_after > 0:
        await asyncio.sleep(min(wait_after / 1000, 120))


_BOT_BLOCK_HTTP_STATUSES = frozenset({403, 429, 503})


def _raise_if_blocked_response(response, url: str) -> None:
    """Surface WAF/bot-block responses distinctly instead of letting the page
    silently render as an error page that later fails with a confusing
    'recipe outdated' selector-not-found message."""
    if response is None:
        return
    status = response.status
    if status in _BOT_BLOCK_HTTP_STATUSES:
        raise RecipeReplayError(
            f"HTTP {status} for {url} — site may be blocking automated access "
            "(not a recipe/selector problem)"
        )


async def _navigate_page(
    page: Page,
    url: str,
    timeout_ms: int,
    *,
    wait_until: str = "domcontentloaded",
) -> None:
    """Navigate with recipe/host wait policy — commit avoids hung domcontentloaded."""
    mode = wait_until if wait_until in _VALID_NAV_WAIT_UNTIL else "domcontentloaded"
    if mode == "commit":
        response = await page.goto(url, timeout=timeout_ms, wait_until="commit")
        _raise_if_blocked_response(response, url)
        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=min(max(timeout_ms // 2, 15_000), 90_000),
            )
        except PlaywrightTimeoutError:
            pass
        return
    response = await page.goto(url, timeout=timeout_ms, wait_until=mode)
    _raise_if_blocked_response(response, url)


def recipe_path_for(parish_key: str, parishes_dir: Path = PARISHES_DIR) -> Path:
    """Return the path to the recipe JSON for *parish_key*.

    Searches diocese subfolders (derry/, down_and_connor/, unknown/, and any
    other subdirectory) before falling back to the legacy flat path so that
    both old flat layouts and the new subfolder layout work transparently.
    """
    recipes_dir = parishes_dir / "recipes"
    # Search existing subdirectories first (new layout)
    for sub in sorted(recipes_dir.iterdir()) if recipes_dir.exists() else []:
        if sub.is_dir():
            candidate = sub / f"{parish_key}.json"
            if candidate.exists():
                return candidate
    # Fall back to flat path (legacy layout or file not yet moved)
    return recipes_dir / f"{parish_key}.json"


def load_recipe(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RecipeReplayError(f"Recipe not found: {path}") from exc
    except Exception as exc:
        raise RecipeReplayError(f"Invalid recipe JSON: {path}") from exc

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RecipeReplayError("Recipe has no steps")
    return data


def _is_pdf_content(data: bytes) -> bool:
    return data[:4] == b"%PDF"


def _is_document_url(url: str) -> bool:
    return is_cloud_document_url(url)


def _normalize_doc_url(url: str) -> str:
    return normalize_document_url(url)


def _office_bytes_look_like_rtf(body: bytes) -> bool:
    return body.lstrip()[:5].startswith(b"{\\rtf")


async def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        suffix = ".rtf" if _office_bytes_look_like_rtf(docx_bytes) else ".docx"
        docx_path = tmp_path / f"bulletin{suffix}"
        out_pdf = tmp_path / "bulletin.pdf"
        docx_path.write_bytes(docx_bytes)
        libreoffice_error = ""

        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(docx_path),
                ],
                capture_output=True,
                timeout=DOCX_CONVERSION_TIMEOUT_S,
            )
            if result.returncode == 0 and out_pdf.exists():
                return out_pdf.read_bytes()
            libreoffice_error = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if suffix == ".rtf":
            extra = f" LibreOffice error: {libreoffice_error}" if libreoffice_error else ""
            raise RecipeReplayError(
                f"Could not convert RTF newsletter to PDF (needs LibreOffice).{extra}"
            )

        try:
            import docx as _docx  # type: ignore[import]
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            suffix = f" LibreOffice error: {libreoffice_error}" if libreoffice_error else ""
            raise RecipeReplayError(
                f"Could not convert DOCX to PDF (missing converter dependencies).{suffix}"
            ) from exc

        doc = _docx.Document(str(docx_path))
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        if not lines:
            raise RecipeReplayError("DOCX has no text content")

        fallback_pdf = tmp_path / "fallback.pdf"
        styles = getSampleStyleSheet()
        pdf_doc = SimpleDocTemplate(
            str(fallback_pdf),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
        )
        story = []
        for line in lines:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Normal"]))
            story.append(Spacer(1, 0.15 * cm))
        pdf_doc.build(story)
        return fallback_pdf.read_bytes()


def _download_source_url(download, page: Page) -> str:
    """Prefer the download's own resource URL over page.url.

    Native browser downloads (e.g. a Wix/GoDaddy ``<a href>`` to a .docx/.pdf
    with no in-page navigation) commonly leave ``page.url`` pointing at the
    listing page the link was clicked from, not the dated file itself. That
    silently defeats URL-based staleness detection (harvester.fetcher calls
    check_bulletin_freshness(result.url, target)) — a 9-week-stale bulletin
    reported as the listing page URL has no date to detect and always passes
    as fresh (found 2026-08-09, parishofhannahstown). ``download.url`` is the
    actual resource the browser fetched and should be used whenever it looks
    like a real document URL.
    """
    try:
        url = (download.url or "").strip()
    except Exception:
        url = ""
    if url and _looks_like_http_url(url):
        return url
    return page.url


async def _save_download_to_pdf(download, dest: Path) -> str:
    suggested = (download.suggested_filename or "").lower()
    if suggested.endswith(".docx") or suggested.endswith(".doc"):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_docx = Path(tmpdir) / "download.docx"
            await download.save_as(str(tmp_docx))
            pdf_bytes = await _convert_docx_to_pdf_bytes(tmp_docx.read_bytes())
            dest.write_bytes(pdf_bytes)
            return "docx_to_pdf"

    await download.save_as(str(dest))
    return "pdf"


async def _download_document_url(
    page: Page,
    raw_url: str,
    dest: Path,
    *,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str]:
    url = _normalize_doc_url(raw_url)
    if _is_non_bulletin_url(url):
        raise RecipeReplayError(f"Refusing non-bulletin document URL: {raw_url}")
    response = await page.request.get(url, timeout=timeout_ms)
    if not response.ok:
        raise RecipeReplayError(f"HTTP {response.status} for {raw_url}")

    body = await response.body()
    content_type = response.headers.get("content-type", "")
    if (
        "text/html" in content_type
        and "drive.usercontent.google.com/download" in url.lower()
        and not _is_pdf_content(body)
    ):
        interstitial_html = body.decode("utf-8", errors="ignore")
        confirm = gdrive_confirm_token(interstitial_html)
        if confirm:
            uuid = gdrive_confirm_uuid(interstitial_html)
            confirm_url = gdrive_download_url_with_confirm(url, confirm, uuid)
            response = await page.request.get(confirm_url, timeout=timeout_ms)
            if not response.ok:
                raise RecipeReplayError(f"HTTP {response.status} for {confirm_url}")
            body = await response.body()
            content_type = response.headers.get("content-type", "")

    path = urlparse(url.lower()).path
    if path.endswith(".docx"):
        pdf_bytes = await _convert_docx_to_pdf_bytes(body)
        dest.write_bytes(pdf_bytes)
        return raw_url, "docx_to_pdf"

    if _is_pdf_content(body):
        dest.write_bytes(body)
        return raw_url, "pdf"

    if body[:3] == b"\xff\xd8\xff" or body[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            from PIL import Image as PILImage
        except ImportError as exc:
            raise RecipeReplayError(
                "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
            ) from exc
        try:
            img = PILImage.open(io.BytesIO(body)).convert("RGB")
            img.save(str(dest), "PDF")
            return raw_url, "image_to_pdf"
        except Exception as exc:
            raise RecipeReplayError(f"Invalid image content for bulletin conversion: {raw_url}") from exc

    if "text/html" in content_type:
        raise RecipeReplayError(f"Server returned HTML instead of document for {raw_url}")

    dest.write_bytes(body)
    return raw_url, "pdf"


async def _click_dropfiles_locator_download(
    page: Page,
    locator,
    dest: Path,
    timeout_ms: int,
) -> tuple[str, str] | None:
    """Click one Dropfiles download locator and convert the result to PDF."""
    try:
        await locator.wait_for(state="visible", timeout=min(timeout_ms, 10_000))
        href = (await locator.get_attribute("href") or "").strip()
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await locator.click(timeout=timeout_ms)
        download = await dl_info.value
        file_type = await _save_download_to_pdf(download, dest)
        source = urljoin(page.url, href) if href else page.url
        return source, file_type
    except Exception:
        return None


def _dropfiles_example_href_from_recipe(recipe: dict) -> str:
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        href = str(step.get("href") or "").strip()
        if href and extract_newsletter_number(href) is not None:
            return href
        url = str(step.get("url") or "").strip()
        if url and extract_newsletter_number(url) is not None:
            return url
    return ""


def _create_connection_ipv4(
    address,
    timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address=None,
    *args,
    **kwargs,
):
    """Connect using A-records only so a blackholed IPv6 never eats the budget.

    GitHub Actions often has AAAA first; urllib then sits on IPv6 until the
    per-attempt timeout and never reaches a working IPv4 path (Limavady /
    Claudy onewebmedia). If the host has no A record, fall back to the
    default resolver (IPv6-only hosts).
    """
    host, port = address
    try:
        addrinfo = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        addrinfo = []
    if not addrinfo:
        return socket.create_connection(address, timeout, source_address, *args, **kwargs)
    err: OSError | None = None
    for family, socktype, proto, _canon, sockaddr in addrinfo:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            else:
                sock.settimeout(socket.getdefaulttimeout())
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            err = exc
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    raise OSError(f"IPv4 connect failed for {host}:{port}")


class _IPv4HTTPConnection(HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _create_connection_ipv4


class _IPv4HTTPSConnection(HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _create_connection_ipv4


class _IPv4HTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_IPv4HTTPConnection, req)


class _IPv4HTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_IPv4HTTPSConnection, req, context=self._context)


def _urlopen_ipv4(request, timeout=None, context=None):
    """urlopen-compatible GET that connects via IPv4 A-records first."""
    if context is None:
        opener = build_opener(_IPv4HTTPHandler, _IPv4HTTPSHandler())
    else:
        opener = build_opener(_IPv4HTTPHandler, _IPv4HTTPSHandler(context=context))
    return opener.open(request, timeout=timeout)


def _ok_http_body(response) -> tuple[bytes, dict[str, str]] | None:
    """Accept HTTP 200, or a body with no status (file:// via FileHandler)."""
    body = response.read()
    status = getattr(response, "status", None)
    if not body or status not in {None, 200}:
        return None
    headers = {k.lower(): v for k, v in response.headers.items()}
    return body, headers


def _fetch_bytes_with_retries(
    url: str,
    *,
    max_attempts: int,
    per_attempt_timeout_s: float,
    total_budget_s: float,
) -> tuple[bytes, dict[str, str]] | None:
    """Plain-HTTP (no browser) GET with retries, run off the event loop.

    See the module-level _DROPFILES_HTTP_* comment for why this exists —
    urllib gets through the sg-captcha challenge far more often than a full
    Playwright navigation to the identical URL. Redirects are followed
    (SEF URL -> index.php?task=frontfile.download -> file). Connects IPv4
    first so a blackholed AAAA cannot burn the attempt. Tries verified TLS
    first; one unverified retry only when the cert is expired / unverifiable.
    Do not raise per_attempt_timeout_s or total_budget_s to paper over this.
    """
    started = time.monotonic()
    attempts = 0
    headers_out = {"User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )}
    url = quote_http_url(url)
    if not url:
        return None
    insecure_ctx: ssl.SSLContext | None = None
    prefer_unverified = False
    while attempts < max_attempts and (time.monotonic() - started) < total_budget_s:
        attempts += 1
        request = Request(url, headers=headers_out)
        try:
            ctx = insecure_ctx if prefer_unverified else None
            with _urlopen_ipv4(
                request, timeout=per_attempt_timeout_s, context=ctx
            ) as response:
                hit = _ok_http_body(response)
                if hit:
                    return hit
        except HTTPError as exc:
            # Missing predicted files are a hard miss — do not burn the
            # shared retry budget on 404/410 (newtownkillea dated uploads).
            if exc.code in {404, 410}:
                return None
        except Exception as exc:
            if prefer_unverified or not _is_certificate_verify_error(exc):
                continue
            # Expired leaf (limavadyparish.org) or missing intermediate
            # (mucknoparish.ie). Retry this URL once without verify.
            prefer_unverified = True
            if insecure_ctx is None:
                insecure_ctx = _insecure_ssl_context()
            try:
                with _urlopen_ipv4(
                    request,
                    timeout=per_attempt_timeout_s,
                    context=insecure_ctx,
                ) as response:
                    hit = _ok_http_body(response)
                    if hit:
                        return hit
            except HTTPError as ssl_exc:
                if ssl_exc.code in {404, 410}:
                    return None
            except Exception:
                pass
    return None


def _dropfiles_body_looks_like_file(headers: dict[str, str], body: bytes) -> bool:
    """Distinguish a real downloaded file from a challenge-passed-through page.

    A successful HTTP 200 through the WAF isn't automatically the right
    answer — a wrong/nonexistent predicted item ID also returns 200, just
    with the ordinary homepage HTML (Joomla silently redirects unknown
    Itemids home) instead of a Content-Disposition: attachment file.
    """
    if not body:
        return False
    content_type = (headers.get("content-type") or "").lower()
    content_disposition = (headers.get("content-disposition") or "").lower()
    if "attachment" in content_disposition:
        return True
    if _is_pdf_content(body) or body[:2] == b"PK" or _office_bytes_look_like_rtf(body):
        return True
    if body[:3] == b"\xff\xd8\xff" or body[:8] == b"\x89PNG\r\n\x1a\n":  # JPEG / PNG
        return True
    if "text/html" in content_type:
        return False
    return content_type.startswith(("application/", "image/"))


async def _save_dropfiles_bytes_to_pdf(
    body: bytes, headers: dict[str, str], url: str, dest: Path
) -> str:
    content_disposition = headers.get("content-disposition") or ""
    name_match = re.search(r'filename="?([^";]+)"?', content_disposition, re.IGNORECASE)
    filename = (name_match.group(1) if name_match else urlparse(url).path).lower()
    if _is_pdf_content(body):
        dest.write_bytes(body)
        return "pdf"
    if filename.endswith((".docx", ".doc")) or body[:2] == b"PK":
        pdf_bytes = await _convert_docx_to_pdf_bytes(body)
        dest.write_bytes(pdf_bytes)
        return "docx_to_pdf"
    if body[:3] == b"\xff\xd8\xff" or body[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            from PIL import Image as PILImage
        except ImportError as exc:
            raise RecipeReplayError(
                "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
            ) from exc
        img = PILImage.open(io.BytesIO(body)).convert("RGB")
        img.save(str(dest), "PDF")
        return "image_to_pdf"
    raise RecipeReplayError(f"Unrecognized Dropfiles file content for {url}")


def _mcn_fetch_newsletter_url(camera_url: str) -> str | None:
    """Plain-HTTP: camera page church id → ProfileDataByJson → newsLetterUrl."""
    html_hit = _fetch_bytes_with_retries(
        camera_url,
        max_attempts=2,
        per_attempt_timeout_s=15,
        total_budget_s=25,
    )
    if not html_hit:
        return None
    body, _headers = html_hit
    church_id = extract_mcn_church_id(body.decode("utf-8", "ignore"))
    if not church_id:
        return None
    api = mcn_profile_data_url(camera_url, church_id)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json",
    }
    try:
        request = Request(api, data=b"{}", method="POST", headers=headers)
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore") or "{}")
    except Exception:
        return None
    return mcn_newsletter_url_from_profile(payload if isinstance(payload, dict) else None)


async def _try_http_document_url(url: str, dest: Path) -> tuple[str, str] | None:
    """Follow redirects and save PDF/DOCX/image without opening Playwright."""
    hit = _fetch_bytes_with_retries(
        url,
        max_attempts=3,
        per_attempt_timeout_s=20,
        total_budget_s=40,
    )
    if not hit:
        return None
    body, headers = hit
    if not _dropfiles_body_looks_like_file(headers, body):
        return None
    try:
        kind = await _save_dropfiles_bytes_to_pdf(body, headers, url, dest)
    except RecipeReplayError:
        return None
    return url, kind


async def _try_mcn_live_newsletter(start_url: str, dest: Path) -> tuple[str, str] | None:
    newsletter_url = await asyncio.to_thread(_mcn_fetch_newsletter_url, start_url)
    if not newsletter_url:
        return None
    return await _try_http_document_url(newsletter_url, dest)


def _churchmedia_fetch_newsletter_url(listing_url: str, slug: str = "") -> str | None:
    """Plain-HTTP: listing slug → getChannelAbout → newsletter_url (no ?cb=)."""
    token = (slug or "").strip() or (churchmedia_slug_from_url(listing_url) or "")
    if not token:
        return None
    api = churchmedia_channel_about_url(token)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        request = Request(api, headers=headers)
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore") or "{}")
    except Exception:
        return None
    return churchmedia_newsletter_url_from_about(
        payload if isinstance(payload, dict) else None
    )


async def _try_churchmedia_newsletter(
    start_url: str,
    dest: Path,
    recipe: dict | None = None,
) -> tuple[str, str] | None:
    """HTTP-first: current churchmedia newsletter, then optional fallback PDFs."""
    slug = ""
    fallbacks: list[str] = []
    if isinstance(recipe, dict):
        slug = str(recipe.get("churchmedia_slug") or "").strip()
        raw_fallbacks = recipe.get("fallback_document_urls") or []
        if isinstance(raw_fallbacks, list):
            fallbacks = [
                str(item).strip()
                for item in raw_fallbacks
                if isinstance(item, str) and str(item).strip()
            ]
    newsletter_url = await asyncio.to_thread(
        _churchmedia_fetch_newsletter_url, start_url, slug
    )
    candidates: list[str] = []
    if newsletter_url:
        candidates.append(newsletter_url)
    for extra in fallbacks:
        if extra not in candidates:
            candidates.append(extra)
    for url in candidates:
        found = await _try_http_document_url(url, dest)
        if found:
            return found
    return None


def _extract_mdocs_dated_downloads(
    html: str,
    base_url: str,
    *,
    year_hint: int,
) -> list[tuple[date, str]]:
    """Pair each mDocs ?mdocs-file= download with the date on its table row."""
    from .bulletin_freshness import extract_bulletin_date

    scored: list[tuple[date, str]] = []
    seen: set[str] = set()
    for row in _MDOCS_TABLE_ROW_RE.findall(html or ""):
        href_match = _MDOCS_DOWNLOAD_HREF_RE.search(row)
        if not href_match:
            continue
        url = urljoin(base_url, href_match.group(1).strip())
        if not url or url in seen or _is_non_bulletin_url(url):
            continue
        text = unquote(re.sub(r"<[^>]+>", " ", row))
        found = (
            extract_date_from_string(text)
            or extract_bulletin_date(text)
            or yearless_slug_date(text, year_hint)
        )
        if found is None:
            continue
        seen.add(url)
        scored.append((found, url))
    return scored


def _pick_newest_mdocs_download(
    scored: list[tuple[date, str]],
    target_date: date,
) -> str | None:
    """Newest dated mDocs file, allowing next-Sunday posts within the scrape window."""
    ahead = target_date + timedelta(days=_HTTP_SCRAPE_AHEAD_DAYS)
    eligible = [(found, url) for found, url in scored if found <= ahead]
    if not eligible:
        return None
    found, url = max(eligible, key=lambda item: (item[0], _mdocs_file_id(item[1])))
    return url


def _mdocs_listing_url_candidates(listing_url: str) -> list[str]:
    """Try the recorded listing, then the opposite HTTP/HTTPS scheme."""
    url = (listing_url or "").strip()
    if not url:
        return []
    out = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        out.append("http://" + url[len("https://") :])
    elif parsed.scheme == "http":
        out.append("https://" + url[len("http://") :])
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


async def _try_http_scrape_mdocs(
    listing_url: str,
    dest: Path,
    target_date: date,
) -> tuple[str, str] | None:
    """Fetch the mDocs listing via plain HTTP and download the newest dated PDF.

    Portstewart (and other Memphis Documents tables) server-render
    ``?mdocs-file=NNNN`` download links. Those URLs have no ``.pdf`` suffix, so
    the generic HTTP-scrape helper misses them, and a Playwright click on the
    title dropdown (``href="#"``) never captures a file.
    """
    for url in _mdocs_listing_url_candidates(listing_url):
        listing_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            url,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_DROPFILES_HTTP_LISTING_BUDGET_S,
        )
        if not listing_result:
            continue
        listing_body, listing_headers = listing_result
        if "text/html" not in (listing_headers.get("content-type") or "").lower():
            continue
        listing_html = listing_body.decode("utf-8", errors="ignore")
        scored = _extract_mdocs_dated_downloads(
            listing_html, url, year_hint=target_date.year
        )
        pdf_url = _pick_newest_mdocs_download(scored, target_date)
        if not pdf_url:
            continue
        found = await _try_http_document_url(pdf_url, dest)
        if found:
            return found
    return None


def _extract_dropfiles_candidates_from_html(html: str, base_url: str) -> list[tuple[int, str]]:
    """Find real mod_downloadlink hrefs in raw listing HTML (no bs4 dependency)."""
    out: list[tuple[int, str]] = []
    for match in _MOD_DOWNLOADLINK_HREF_RE.finditer(html):
        href = match.group(1) or match.group(2)
        if not href:
            continue
        absolute = urljoin(base_url, href)
        id_match = _DROPFILES_FILE_ID_RE.search(absolute)
        if id_match:
            out.append((int(id_match.group(1)), absolute))
    return out


def _dropfiles_download_url_variants(url: str) -> list[str]:
    """SEF Dropfiles href plus the unblocked ``task=frontfile.download`` form."""
    out: list[str] = []
    url = (url or "").strip()
    if url:
        out.append(url)
    task = dropfiles_task_download_url(url)
    if task and task not in out:
        out.append(task)
    return out


_WIX_ERROR_PAGE_RE = re.compile(
    r"page you.?re looking for|isn.?t here|doesn.?t exist|errorPage|wix-error",
    re.IGNORECASE,
)


def _wix_html_looks_live(url: str, headers: dict[str, str], body: bytes) -> bool:
    """True when a Wix dated-slug GET is a real bulletin page, not a 404 shell."""
    if not body:
        return False
    if body[:4] == b"%PDF":
        return True
    if len(body) < 80_000:
        return False
    ct = (headers.get("content-type") or "").lower()
    if "html" not in ct and not body[:30].lower().lstrip().startswith((b"<!doctype", b"<html")):
        return False
    text = body.decode("utf-8", errors="replace")
    if _WIX_ERROR_PAGE_RE.search(text[:20_000]):
        return False
    leaf = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    leaf = re.sub(r"^copy-of-", "", leaf, flags=re.IGNORECASE)
    slug_bits = leaf.replace("-", "_")
    return bool(slug_bits) and slug_bits.lower() in text.lower().replace("-", "_")


async def _try_resolve_wix_dated_slug(
    example_urls: list[str],
    target_date: date,
    *,
    weeks_back: int = 3,
) -> str | None:
    """HTTP-probe canonical and ``copy-of-`` Wix slugs; return the first live page."""
    candidates: list[str] = []
    for example in example_urls:
        example = (example or "").strip()
        if not example:
            continue
        for url in wix_dated_slug_candidates(
            example, target_date, weeks_back=weeks_back
        ):
            if url not in candidates:
                candidates.append(url)
    for url in candidates:
        result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            url,
            max_attempts=2,
            per_attempt_timeout_s=8.0,
            total_budget_s=10.0,
        )
        if not result:
            continue
        body, headers = result
        if _wix_html_looks_live(url, headers, body):
            return url
    return None


async def _try_dropfiles_predicted_downloads(
    page: Page,
    dest: Path,
    example_href: str,
    timeout_ms: int,
    *,
    target_date: date | None,
) -> tuple[str, str] | None:
    """Fallback 3 for WAF-flaky Joomla Dropfiles sites (threepatrons.org,
    stmarysportglenone.org — same SiteGround-hosted sg-captcha challenge).

    Tier 1: plain-HTTP-retry the listing page itself (bypasses the browser
            fingerprint the WAF flags) and parse out the REAL newest
            mod_downloadlink href — preferred over guessing, since the site
            doesn't always post on the expected weekly cadence (confirmed
            2026-08-10: stmarysportglenone.org was still one Sunday behind).
    Tier 2: if the listing itself can't be fetched within budget, fall back
            to sequential-ID + liturgical-title URL prediction (existing
            predict_dropfiles_bulletin_urls), each tried via plain-HTTP-retry.
    Tier 3: last resort, the original browser-navigation probe — kept in case
            some other WAF variant responds better to a real browser.
    """
    if target_date is None:
        return None
    started = time.monotonic()

    def _remaining_budget(safety_margin_s: float = 5.0) -> float:
        return _DROPFILES_HTTP_OVERALL_BUDGET_S - (time.monotonic() - started) - safety_margin_s

    listing_url = page.url if page and _looks_like_http_url(page.url) else ""
    if listing_url and _remaining_budget() > 0:
        listing_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            listing_url,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=min(_DROPFILES_HTTP_LISTING_BUDGET_S, _remaining_budget()),
        )
        if listing_result:
            listing_body, listing_headers = listing_result
            if "text/html" in (listing_headers.get("content-type") or "").lower():
                html = listing_body.decode("utf-8", errors="ignore")
                candidates = _extract_dropfiles_candidates_from_html(html, listing_url)
                if candidates and _remaining_budget() > 0:
                    _best_id, best_url = max(candidates)
                    for file_url in _dropfiles_download_url_variants(best_url):
                        if _remaining_budget() <= 0:
                            break
                        file_result = await asyncio.to_thread(
                            _fetch_bytes_with_retries,
                            file_url,
                            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                            total_budget_s=min(_DROPFILES_HTTP_FILE_BUDGET_S, _remaining_budget()),
                        )
                        if not file_result:
                            continue
                        file_body, file_headers = file_result
                        if _dropfiles_body_looks_like_file(file_headers, file_body):
                            try:
                                file_type = await _save_dropfiles_bytes_to_pdf(
                                    file_body, file_headers, file_url, dest
                                )
                                return file_url, file_type
                            except RecipeReplayError:
                                continue

    if example_href:
        predicted: list[str] = []
        for candidate in predict_dropfiles_bulletin_urls(example_href, target_date)[:4]:
            for variant in _dropfiles_download_url_variants(candidate):
                if variant not in predicted:
                    predicted.append(variant)
        for candidate in predicted:
            if _remaining_budget() <= 0:
                break
            candidate_result = await asyncio.to_thread(
                _fetch_bytes_with_retries,
                candidate,
                max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                total_budget_s=min(_DROPFILES_HTTP_PREDICTED_BUDGET_S, _remaining_budget()),
            )
            if not candidate_result:
                continue
            candidate_body, candidate_headers = candidate_result
            if not _dropfiles_body_looks_like_file(candidate_headers, candidate_body):
                continue
            try:
                file_type = await _save_dropfiles_bytes_to_pdf(
                    candidate_body, candidate_headers, candidate, dest
                )
                return candidate, file_type
            except RecipeReplayError:
                continue

    if not example_href:
        return None

    # Tier 3 (last resort): original browser-navigation probe.
    probe_timeout_ms = min(max(int(timeout_ms), 1), 12_000)
    block_hits = 0
    for candidate in predict_dropfiles_bulletin_urls(example_href, target_date)[:6]:
        # Direct browser download only — do not recurse into listing discovery.
        try:
            async with page.expect_download(timeout=probe_timeout_ms) as dl_info:
                response = await page.goto(
                    candidate, timeout=probe_timeout_ms, wait_until="commit"
                )
            if response is not None and response.status in _BOT_BLOCK_HTTP_STATUSES:
                block_hits += 1
                if block_hits >= 2:
                    return None
                continue
            download = await dl_info.value
            file_type = await _save_download_to_pdf(download, dest)
            return candidate, file_type
        except Exception:
            pass
        try:
            return await _download_document_url(
                page, candidate, dest, timeout_ms=probe_timeout_ms
            )
        except RecipeReplayError as exc:
            if "blocking automated access" in str(exc).lower() or "HTTP 403" in str(exc):
                block_hits += 1
                if block_hits >= 2:
                    return None
            continue
    return None


_PDFEMB_IFRAME_SRC_RE = re.compile(
    r'\bpdfembed-iframe\b[^>]*\bsrc="([^"]+)"|\bsrc="([^"]+)"[^>]*\bpdfembed-iframe\b',
    re.IGNORECASE,
)
_WP_UPLOAD_IMAGE_RE = re.compile(
    r"wp-content/uploads/(20\d{2})/(0[1-9]|1[0-2])/([A-Za-z0-9_.%-]+\.(?:png|jpe?g))",
    re.IGNORECASE,
)
_RESIZED_IMAGE_SUFFIX_RE = re.compile(r"-\d+x\d+\.(?:png|jpe?g)$", re.IGNORECASE)


def _href_match_blob(url: str) -> str:
    """Lowercased href with %20/spaces folded to hyphens for pattern checks.

    Muckno filenames are usually hyphenated (clontibret-muckno-bulletin) but
    the same words can appear as ``F Clontibret Muckno Bulletin 23rd AUG.pdf``.
    """
    return unquote(url or "").lower().replace(" ", "-")


def _is_certificate_verify_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    text = f"{type(reason).__name__ if reason is not None else ''} {reason} {exc}".lower()
    return (
        "certificate_verify" in text
        or "certificate verify failed" in text
        or "sslcertverificationerror" in text
        or "certificate has expired" in text
        or "certificate expired" in text
    )


def _insecure_ssl_context() -> ssl.SSLContext:
    """Last-resort context for parish hosts that omit the CA intermediate.

    mucknoparish.ie (proved 23/08/2026) sends only the leaf cert signed by
    Sectigo Public Server Authentication CA DV R36. urlopen then fails with
    CERTIFICATE_VERIFY_FAILED and the scrape reports a false 'no PDF'.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_A_HREF_WITH_TEXT_RE = re.compile(
    r"""<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>(.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_IFRAME_OR_EMBED_SRC_RE = re.compile(
    r"""<(?:iframe|embed)\b[^>]*?\bsrc=["']([^"']+)["']""",
    re.IGNORECASE,
)
_OBJECT_DATA_RE = re.compile(
    r"""<object\b[^>]*?\bdata=["']([^"']+)["']""",
    re.IGNORECASE,
)
_QUERY_URL_PARAM_RE = re.compile(r"""[?&]url=([^&"'#\s]+)""", re.IGNORECASE)


def _listing_src_to_file_url(raw: str, base_url: str) -> str:
    """Turn an iframe src / viewer wrapper / url= value into the real file URL."""
    text = (raw or "").strip()
    if not text:
        return ""
    absolute = urljoin(base_url, text)
    unwrapped = unwrap_docs_viewer_url(absolute)
    if unwrapped and unwrapped != absolute:
        return unwrapped
    decoded = unquote(text)
    if decoded.lower().startswith(("http://", "https://")):
        return unwrap_docs_viewer_url(decoded) or decoded
    return urljoin(base_url, decoded)


def _anchor_inner_text(inner: str) -> str:
    text = re.sub(r"<[^>]+>", " ", inner or "")
    return re.sub(r"\s+", " ", text).strip()


def _extract_matching_href_texts(
    html: str, base_url: str, keyword_patterns: list[str]
) -> list[tuple[str, str]]:
    """Return (absolute_href, link_text) pairs for matching listing links.

    Hashed One.com files (Galloon / Newtownbutler ``S25C-*.pdf``) have no
    date in the URL — the Sunday is only in the anchor text. Keep href-only
    leftovers so PDF Embedder / bare ``href`` still scrape.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    patterns = [str(p).lower() for p in keyword_patterns if p]

    def _want(href: str) -> bool:
        if not patterns:
            return False
        blob = _href_match_blob(href)
        return any(pat in blob for pat in patterns)

    for href, inner in _A_HREF_WITH_TEXT_RE.findall(html or ""):
        if not _want(href):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, _anchor_inner_text(inner)))
    for href in re.findall(r"""href=["']([^"']+)["']""", html or "", re.IGNORECASE):
        if not _want(href):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, ""))
    extra_raw: list[str] = []
    extra_raw.extend(_IFRAME_OR_EMBED_SRC_RE.findall(html or ""))
    extra_raw.extend(_OBJECT_DATA_RE.findall(html or ""))
    extra_raw.extend(_QUERY_URL_PARAM_RE.findall(html or ""))
    for raw in extra_raw:
        file_url = _listing_src_to_file_url(raw, base_url)
        if not file_url:
            continue
        if not (_want(file_url) or _want(raw)):
            continue
        if file_url in seen:
            continue
        seen.add(file_url)
        out.append((file_url, ""))
    return out


def _extract_matching_hrefs(html: str, base_url: str, keyword_patterns: list[str]) -> list[str]:
    """Plain-regex href extraction (no bs4 dependency) for WAF-flaky sites where
    we fetch raw HTML via plain HTTP retries instead of a Playwright DOM."""
    out: list[str] = []
    seen: set[str] = set()
    patterns = [str(p).lower() for p in keyword_patterns if p]
    for href in re.findall(r"""href=["']([^"']+)["']""", html, re.IGNORECASE):
        blob = _href_match_blob(href)
        if not any(pat in blob for pat in patterns):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


# Harvest Sunday is last Sunday Mon–Sat. Parishes sometimes post next
# Sunday's file on Thursday/Friday (milfordrathmullanparishes 2026-08-21:
# the listing only had Parish-Newsletter-Sunday-23rd-August.pdf). A +3
# cutoff rejected that as "too new" and reported a false miss.
_HTTP_SCRAPE_AHEAD_DAYS = 7


def _http_scrape_item_date(text: str, target_date: date) -> date | None:
    """Date from a URL or listing-page label. Empty text is a miss."""
    from .bulletin_freshness import extract_bulletin_date

    blob = (text or "").strip()
    if not blob:
        return None
    # Prefer the filename's own date over WordPress /uploads/YYYY/MM/
    # folder dates — Malin uploads March bulletins into /2026/04/, and
    # extract_bulletin_date then treats "29th-March" as 29/04.
    return (
        extract_date_from_string(blob)
        or liturgical_date_from_text(
            blob, year_hint_from_upload_url(blob, target_date.year)
        )
        or extract_bulletin_date(blob)
        or yearless_slug_date(blob, target_date.year, near=target_date)
    )


def _score_http_scrape_pdf_hrefs(
    hrefs: list[str],
    target_date: date,
    labels: dict[str, str] | None = None,
) -> list[tuple[date, str]]:
    """Rank listing-page PDF hrefs by extracted bulletin date.

    Drops non-bulletin URLs (Order of Mass, GDPR, …) and anything dated
    more than a week after the harvest Sunday. Yearless slugs such as
    Parish-Newsletter-Sunday-9th-August.pdf are dated with the harvest year.
    When the URL has no date (hashed ``S25C-*.pdf``, ``Aug 16  2026.pdf``),
    score the listing link text if one was passed.
    """
    scored: list[tuple[date, str]] = []
    ahead = target_date + timedelta(days=_HTTP_SCRAPE_AHEAD_DAYS)
    for href in hrefs:
        if _is_non_bulletin_url(href):
            continue
        path = urlparse(href).path.lower()
        if not path.endswith((".pdf", ".docx", ".doc", ".rtf")):
            continue
        found = _http_scrape_item_date(href, target_date)
        if not found and labels:
            found = _http_scrape_item_date(labels.get(href, ""), target_date)
        if found and found <= ahead:
            scored.append((found, href))
    return scored


def _newest_dated_post_url_from_listing(
    html: str,
    base_url: str,
    post_slug_patterns: list[str],
    target_date: date,
) -> str | None:
    """Pick the newest dated HTML post from a category/listing page.

    Used when the listing itself has no PDF hrefs (Muckno weekly-bulletin
    archive: this week's file is only on the post page).
    """
    if not html or not post_slug_patterns:
        return None
    hrefs = _extract_matching_hrefs(html, base_url, post_slug_patterns)
    scored = _score_wordpress_post_hrefs(hrefs, target_date)
    if not scored:
        return None
    return max(scored)[1]


async def _try_http_scrape_newest_pdf(
    listing_url: str,
    dest: Path,
    *,
    href_patterns: list[str],
    target_date: date,
    post_slug_patterns: list[str] | None = None,
) -> tuple[str, str] | None:
    """Fetch a listing page via plain HTTP and download the newest matching PDF.

    Built for Extra/Divi toggle pages (milfordrathmullanparishes.ie) where the
    Parish-Newsletter PDF is in the HTML but hidden inside a closed accordion,
    so Playwright ``visible`` waits time out. The listing itself is not WAF
    blocked — we just must not click.

    If the listing has no matching PDF hrefs and *post_slug_patterns* is set
    (Castleblayney / Muckno), follow the newest dated post and scrape that
    page for the PDF instead of pinning a filename.
    """
    listing_html = ""
    listing_fetched_from = listing_url
    for candidate in _mdocs_listing_url_candidates(listing_url):
        listing_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            candidate,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_DROPFILES_HTTP_LISTING_BUDGET_S,
        )
        if not listing_result:
            continue
        listing_body, listing_headers = listing_result
        if "text/html" not in (listing_headers.get("content-type") or "").lower():
            continue
        listing_html = listing_body.decode("utf-8", errors="ignore")
        listing_fetched_from = candidate
        break
    if not listing_html:
        return None
    listing_pairs = _extract_matching_href_texts(
        listing_html, listing_fetched_from, href_patterns
    )
    hrefs = [href for href, _text in listing_pairs]
    labels = {href: text for href, text in listing_pairs if text}
    scored = _score_http_scrape_pdf_hrefs(hrefs, target_date, labels=labels)
    if not scored:
        post_url = _newest_dated_post_url_from_listing(
            listing_html,
            listing_fetched_from,
            [str(p).strip() for p in (post_slug_patterns or []) if str(p).strip()],
            target_date,
        )
        if not post_url:
            return None
        post_html = ""
        post_fetched_from = post_url
        for post_candidate in _mdocs_listing_url_candidates(post_url):
            post_result = await asyncio.to_thread(
                _fetch_bytes_with_retries,
                post_candidate,
                max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                total_budget_s=_DROPFILES_HTTP_FILE_BUDGET_S,
            )
            if not post_result:
                continue
            post_body, post_headers = post_result
            if "text/html" not in (post_headers.get("content-type") or "").lower():
                continue
            post_html = post_body.decode("utf-8", errors="ignore")
            post_fetched_from = post_candidate
            break
        if not post_html:
            return None
        post_pairs = _extract_matching_href_texts(
            post_html, post_fetched_from, href_patterns
        )
        hrefs = [href for href, _text in post_pairs]
        labels = {href: text for href, text in post_pairs if text}
        scored = _score_http_scrape_pdf_hrefs(hrefs, target_date, labels=labels)
    if not scored:
        return None
    _best_date, pdf_url = max(scored)
    pdf_url = quote_http_url(pdf_url)
    file_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        pdf_url,
        max_attempts=_DROPFILES_HTTP_ATTEMPTS,
        per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
        total_budget_s=_DROPFILES_HTTP_FILE_BUDGET_S,
    )
    if not file_result:
        return None
    file_body, file_headers = file_result
    is_rtf = _office_bytes_look_like_rtf(file_body) or urlparse(pdf_url).path.lower().endswith(".rtf")
    if not (
        _dropfiles_body_looks_like_file(file_headers, file_body)
        and (_is_pdf_content(file_body) or file_body[:2] == b"PK" or is_rtf)
    ):
        return None
    if is_rtf or (file_body[:2] == b"PK" and not _is_pdf_content(file_body)):
        pdf_bytes = await _convert_docx_to_pdf_bytes(file_body)
        dest.write_bytes(pdf_bytes)
        return pdf_url, "docx_to_pdf"
    dest.write_bytes(file_body)
    return pdf_url, "pdf"


async def _try_predicted_dated_pdf(
    example_url: str,
    dest: Path,
    target_date: date,
    *,
    weeks_back: int = 8,
    weeks_ahead: int = 0,
) -> tuple[str, str] | None:
    """Try rewrite_date_url guesses for *target_date* and nearby Sundays.

    Skips any listing page entirely — used when the HTML index is
    Cloudflare-challenged but ``wp-content/uploads`` dated files are not
    (newtownkilleaparish.ie). *weeks_ahead* (recipe key ``weeks_ahead``)
    tries next Sunday first when this week's file is already the next one.
    """
    for url in predicted_dated_upload_urls(
        example_url,
        target_date,
        weeks_back=weeks_back,
        weeks_ahead=weeks_ahead,
    ):
        file_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            url,
            max_attempts=3,
            per_attempt_timeout_s=8.0,
            total_budget_s=12.0,
        )
        if not file_result:
            continue
        file_body, file_headers = file_result
        if _dropfiles_body_looks_like_file(file_headers, file_body):
            if _is_pdf_content(file_body):
                dest.write_bytes(file_body)
                return url, "pdf"
            if file_body[:2] == b"PK":
                pdf_bytes = await _convert_docx_to_pdf_bytes(file_body)
                dest.write_bytes(pdf_bytes)
                return url, "docx_to_pdf"
            continue
        # Dated notice pages (Holywood): HTML with a PDF Embedder iframe,
        # not a direct upload. 404s are already a hard miss above.
        if _body_looks_like_html(file_headers, file_body):
            found = await _download_pdfembed_from_html(
                file_body.decode("utf-8", errors="ignore"),
                url,
                dest,
                max_attempts=3,
                per_attempt_timeout_s=8.0,
                total_budget_s=12.0,
            )
            if found:
                return found
    return None


_SKIP_IMAGE_NAME_RE = re.compile(
    r"screenshot|logo|icon|favicon|crest|cropped-|banner|avatar",
    re.IGNORECASE,
)


def _href_matches_patterns(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    blob = _href_match_blob(url)
    return any(pat.lower().replace(" ", "-") in blob for pat in patterns)


async def _try_wp_json_newest_media(
    start_url: str,
    dest: Path,
    *,
    href_patterns: list[str],
    target_date: date,
) -> tuple[str, str] | None:
    """Download the newest dated media PDF from /wp-json/wp/v2/media.

    Built for All Saints Ballymena: the public bulletin page still links a
    2025 Wedding-Parish.pdf, but the media library has this week's
    16.8.26-20th-Sunday.pdf (confirmed 2026-08-18). Never opens Playwright.
    """
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    api = (
        f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/media"
        "?per_page=20&orderby=date&order=desc"
    )
    result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        api,
        max_attempts=6,
        per_attempt_timeout_s=10.0,
        total_budget_s=25.0,
    )
    if not result:
        return None
    body, headers = result
    ct = (headers.get("content-type") or "").lower()
    if "json" not in ct and not body[:1] == b"[":
        return None
    try:
        items = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    hrefs: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source_url") or "").strip()
        slug = str(item.get("slug") or "")
        title = ""
        raw_title = item.get("title")
        if isinstance(raw_title, dict):
            title = str(raw_title.get("rendered") or "")
        blob = f"{src} {slug} {title}"
        if not src or _is_non_bulletin_url(src):
            continue
        if href_patterns and not _href_matches_patterns(blob, href_patterns):
            continue
        hrefs.append(src)
    scored = _score_http_scrape_pdf_hrefs(hrefs, target_date)
    if not scored:
        return None
    _best_date, pdf_url = max(scored)
    pdf_url = quote_http_url(pdf_url)
    file_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        pdf_url,
        max_attempts=4,
        per_attempt_timeout_s=10.0,
        total_budget_s=20.0,
    )
    if not file_result:
        return None
    file_body, file_headers = file_result
    if not (
        _dropfiles_body_looks_like_file(file_headers, file_body)
        and (_is_pdf_content(file_body) or file_body[:2] == b"PK")
    ):
        return None
    if file_body[:2] == b"PK" and not _is_pdf_content(file_body):
        pdf_bytes = await _convert_docx_to_pdf_bytes(file_body)
        dest.write_bytes(pdf_bytes)
        return pdf_url, "docx_to_pdf"
    dest.write_bytes(file_body)
    return pdf_url, "pdf"


_RSS_ITEM_RE = re.compile(r"<item\b.*?</item>", re.IGNORECASE | re.DOTALL)
_RSS_LINK_RE = re.compile(r"<link>\s*(https?://[^<\s]+)\s*</link>", re.IGNORECASE)


def _normalize_wp_post_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def _score_wordpress_post_hrefs(
    hrefs: list[str],
    target_date: date,
) -> list[tuple[date, str]]:
    scored: list[tuple[date, str]] = []
    for href in hrefs:
        slug = urlparse(href).path.rstrip("/").rsplit("/", 1)[-1]
        found = (
            extract_date_from_slug(slug)
            or extract_date_from_string(slug)
            or liturgical_date_from_text(slug, target_date.year)
        )
        if found and found <= target_date + timedelta(days=3):
            scored.append((found, href))
    return scored


def _pick_newest_dated_post_url(
    hrefs: list[str],
    target_date: date,
) -> str | None:
    scored = _score_wordpress_post_hrefs(hrefs, target_date)
    if scored:
        return max(scored)[1]
    return hrefs[0] if hrefs else None


def _wordpress_post_records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        posts = payload.get("posts")
        if isinstance(posts, list):
            return [item for item in posts if isinstance(item, dict)]
    return []


def _wordpress_post_links_from_payload(
    payload: object,
    slug_patterns: list[str],
) -> list[str]:
    """Collect public permalinks from wp-json / WP.com public-api JSON."""
    out: list[str] = []
    seen: set[str] = set()
    for item in _wordpress_post_records(payload):
        link = str(item.get("link") or item.get("URL") or "").strip()
        slug = str(item.get("slug") or "")
        raw_title = item.get("title")
        if isinstance(raw_title, dict):
            title = str(raw_title.get("rendered") or "")
        else:
            title = str(raw_title or "")
        blob = f"{link} {slug} {title}".lower()
        if not link or not _href_matches_patterns(blob, slug_patterns):
            continue
        norm = _normalize_wp_post_url(link)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _wordpress_feed_post_links(xml: str, slug_patterns: list[str]) -> list[str]:
    """Item permalinks from a WordPress RSS feed."""
    out: list[str] = []
    seen: set[str] = set()
    for item in _RSS_ITEM_RE.findall(xml or ""):
        match = _RSS_LINK_RE.search(item)
        if not match:
            continue
        link = match.group(1).strip()
        if not _href_matches_patterns(link, slug_patterns):
            continue
        norm = _normalize_wp_post_url(link)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _wordpress_posts_api_urls(start_url: str) -> list[str]:
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    host = parsed.netloc
    query = "per_page=10&orderby=date&order=desc"
    return [
        f"{origin}/wp-json/wp/v2/posts?{query}",
        f"https://public-api.wordpress.com/wp/v2/sites/{host}/posts?{query}",
        f"{origin}/?rest_route=/wp/v2/posts&{query}",
    ]


def _listing_wordpress_post_links(
    html: str,
    base_url: str,
    slug_patterns: list[str],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    base_host = urlparse(base_url).netloc.lower()
    for href in _extract_matching_hrefs(html, base_url, slug_patterns):
        parsed = urlparse(href)
        if parsed.netloc.lower() != base_host:
            continue
        if parsed.query or "/feed/" in parsed.path.lower():
            continue
        norm = _normalize_wp_post_url(href)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _extract_post_page_images(html: str, base_url: str) -> list[str]:
    """Full-size upload images on one post page, any upload month.

    Skip logos and WordPress resized variants. A July-posted August bulletin
    can live under /uploads/2026/07/ while the slug Sunday is in August.
    """
    out: list[str] = []
    seen: set[str] = set()
    for match in _WP_UPLOAD_IMAGE_RE.finditer(html or ""):
        year, month, name = int(match.group(1)), int(match.group(2)), match.group(3)
        if _SKIP_IMAGE_NAME_RE.search(name) or _RESIZED_IMAGE_SUFFIX_RE.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(urljoin(base_url, f"/wp-content/uploads/{year}/{month:02d}/{name}"))
    return out


async def _try_wp_json_newest_post_images(
    start_url: str,
    dest: Path,
    *,
    slug_patterns: list[str],
    target_date: date,
    example_post_url: str | None = None,
    weeks_back: int = 3,
    image_count: int = 2,
) -> tuple[str, str] | None:
    """Find the newest Sunday bulletin post, then stack its page images.

    Built for stteresasparish.church: WordPress.com hides on-site /wp-json/
    (HTML 404) but public-api.wordpress.com and /feed/ list real posts.
    The permalink folder is the *post* date, a few days before the Sunday
    in the slug — prefer JSON/RSS/listing over guessing that folder.

    If this Sunday's post is missing, returns the newest older Sunday
    (freshness then stale-rejects or grace-accepts it). Never invents a
    16 Aug URL when only 9 Aug exists.
    """
    wanted = max(1, image_count)
    candidates: list[str] = []

    def _remember(url: str) -> None:
        norm = _normalize_wp_post_url(url)
        if norm and norm not in candidates:
            candidates.append(norm)

    for api in _wordpress_posts_api_urls(start_url):
        result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            api,
            max_attempts=4,
            per_attempt_timeout_s=10.0,
            total_budget_s=18.0,
        )
        if not result:
            continue
        body, headers = result
        ct = (headers.get("content-type") or "").lower()
        if "json" not in ct and body[:1] not in {b"[", b"{"}:
            continue
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        for link in _wordpress_post_links_from_payload(payload, slug_patterns):
            _remember(link)
        if candidates:
            break

    if not candidates:
        parsed = urlparse(start_url)
        feed_url = f"{parsed.scheme}://{parsed.netloc}/feed/"
        feed_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            feed_url,
            max_attempts=4,
            per_attempt_timeout_s=10.0,
            total_budget_s=15.0,
        )
        if feed_result:
            feed_body, feed_headers = feed_result
            feed_ct = (feed_headers.get("content-type") or "").lower()
            if (
                "xml" in feed_ct
                or "rss" in feed_ct
                or feed_body.lstrip()[:5] in {b"<?xml", b"<rss ", b"<feed"}
            ):
                xml = feed_body.decode("utf-8", errors="ignore")
                for link in _wordpress_feed_post_links(xml, slug_patterns):
                    _remember(link)

    if not candidates:
        listing_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            start_url,
            max_attempts=4,
            per_attempt_timeout_s=10.0,
            total_budget_s=15.0,
        )
        if listing_result:
            listing_body, listing_headers = listing_result
            if "html" in (listing_headers.get("content-type") or "").lower():
                listing_html = listing_body.decode("utf-8", errors="ignore")
                for link in _listing_wordpress_post_links(
                    listing_html, start_url, slug_patterns
                ):
                    _remember(link)

    picked = _pick_newest_dated_post_url(candidates, target_date)
    probe_urls: list[str] = []
    if picked:
        probe_urls.append(picked)
    if example_post_url:
        for url in predicted_wordpress_dated_post_urls(
            example_post_url, target_date, weeks_back=weeks_back
        ):
            if url not in probe_urls:
                probe_urls.append(url)
    if not probe_urls:
        return None

    for post_url in probe_urls:
        post_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            post_url,
            max_attempts=3,
            per_attempt_timeout_s=10.0,
            total_budget_s=14.0,
        )
        if not post_result:
            continue
        post_body, post_headers = post_result
        if "html" not in (post_headers.get("content-type") or "").lower():
            continue
        post_html = post_body.decode("utf-8", errors="ignore")
        image_urls = _extract_post_page_images(post_html, post_url)[:wanted]
        if len(image_urls) < wanted:
            continue
        image_bytes: list[bytes] = []
        for image_url in image_urls:
            image_result = await asyncio.to_thread(
                _fetch_bytes_with_retries,
                image_url,
                max_attempts=3,
                per_attempt_timeout_s=10.0,
                total_budget_s=14.0,
            )
            if not image_result:
                continue
            image_body, image_headers = image_result
            if _dropfiles_body_looks_like_file(image_headers, image_body):
                image_bytes.append(image_body)
        if len(image_bytes) < wanted:
            continue
        await _images_bytes_to_pdf(dest, image_bytes[:wanted])
        return post_url, "image_to_pdf"
    return None


def _extract_scored_upload_images(
    html: str,
    base_url: str,
    *,
    href_patterns: list[str],
    target_date: date,
) -> list[tuple[date, str]]:
    """Newest-first bulletin page images from raw HTML (no Playwright)."""
    from .bulletin_freshness import extract_bulletin_date

    scored: list[tuple[date, str]] = []
    seen: set[str] = set()
    for match in _WP_UPLOAD_IMAGE_RE.finditer(html):
        year, month, name = int(match.group(1)), int(match.group(2)), match.group(3)
        if _RESIZED_IMAGE_SUFFIX_RE.search(name) or _SKIP_IMAGE_NAME_RE.search(name):
            continue
        url = urljoin(base_url, f"/wp-content/uploads/{year}/{month:02d}/{name}")
        if url in seen:
            continue
        seen.add(url)
        if href_patterns and not _href_matches_patterns(url, href_patterns):
            continue
        if _is_non_bulletin_url(url):
            continue
        found = (
            extract_date_from_string(name)
            or liturgical_date_from_text(name, year)
            or extract_bulletin_date(url)
            or date(year, month, 1)
        )
        if found <= target_date + timedelta(days=3):
            scored.append((found, url))
    return scored


async def _try_http_scrape_newest_images(
    listing_url: str,
    dest: Path,
    *,
    href_patterns: list[str],
    target_date: date,
    count: int = 1,
) -> tuple[str, str] | None:
    """Fetch listing HTML and stack the newest week's page images into a PDF.

    Built for Derriaghy (Playwright navigation times out) and Iskaheen
    (stacked August scans on /bulletin). Never opens a browser.
    """
    listing_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        listing_url,
        max_attempts=_DROPFILES_HTTP_ATTEMPTS,
        per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
        total_budget_s=_DROPFILES_HTTP_LISTING_BUDGET_S,
    )
    if not listing_result:
        return None
    listing_body, listing_headers = listing_result
    if "text/html" not in (listing_headers.get("content-type") or "").lower():
        return None
    listing_html = listing_body.decode("utf-8", errors="ignore")
    scored = _extract_scored_upload_images(
        listing_html,
        listing_url,
        href_patterns=href_patterns,
        target_date=target_date,
    )
    if not scored:
        return None
    best_date = max(item[0] for item in scored)
    # Keep document order so stacked pages stay page-1, page-2.
    week_urls = [url for found, url in scored if found == best_date]
    week_urls = week_urls[: max(1, count)]
    image_bytes: list[bytes] = []
    source_url = week_urls[0]
    for image_url in week_urls:
        image_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            image_url,
            max_attempts=4,
            per_attempt_timeout_s=10.0,
            total_budget_s=20.0,
        )
        if not image_result:
            continue
        image_body, image_headers = image_result
        if _dropfiles_body_looks_like_file(image_headers, image_body):
            image_bytes.append(image_body)
            source_url = image_url
    if not image_bytes:
        return None
    await _images_bytes_to_pdf(dest, image_bytes)
    return source_url, "image_to_pdf"


def _body_looks_like_html(headers: dict[str, str], body: bytes) -> bool:
    """True when a 200 response is an HTML page rather than a file download."""
    if not body:
        return False
    content_type = (headers.get("content-type") or "").lower()
    if "html" in content_type:
        return True
    head = body.lstrip()[:64].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _decode_pdfemb_data_url(raw: str) -> str | None:
    """Decode PDF Embedder Premium ``pdfemb-data`` (base64 JSON ``{url:...}``)."""
    text = unquote((raw or "").strip()).replace(" ", "+")
    if not text:
        return None
    pad = "=" * ((4 - len(text) % 4) % 4)
    payload = None
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            payload = json.loads(decoder(text + pad))
            break
        except Exception:
            continue
    if not isinstance(payload, dict):
        return None
    url = payload.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _extract_pdfembed_target_url(html: str) -> str | None:
    """PDF Embedder plugin iframe target PDF.

    Older builds: ``src="...?url=<urlencoded pdf url>&title=..."``.
    Premium builds (Holywood): ``src="...?pdfemb-data=<base64 json {url:...}>"``.
    Same plugin/markup as PDFEMB_SELECTOR (a.pdfemb-viewer) used elsewhere,
    just accessed via raw HTML regex instead of a Playwright locator.
    """
    m = _PDFEMB_IFRAME_SRC_RE.search(html or "")
    if not m:
        return None
    src = (m.group(1) or m.group(2) or "").replace("&amp;", "&").strip()
    if not src:
        return None
    query = parse_qs(urlparse(unquote(src)).query)
    urls = query.get("url")
    if urls and urls[0]:
        return urls[0]
    for raw in query.get("pdfemb-data") or []:
        decoded = _decode_pdfemb_data_url(raw)
        if decoded:
            return decoded
    return None


async def _download_pdfembed_from_html(
    html: str,
    page_url: str,
    dest: Path,
    *,
    max_attempts: int,
    per_attempt_timeout_s: float,
    total_budget_s: float,
) -> tuple[str, str] | None:
    """Download the PDF Embedder iframe target from an already-fetched post."""
    pdf_url = _extract_pdfembed_target_url(html)
    if not pdf_url:
        return None
    pdf_url = urljoin(page_url, pdf_url)
    file_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        pdf_url,
        max_attempts=max_attempts,
        per_attempt_timeout_s=per_attempt_timeout_s,
        total_budget_s=total_budget_s,
    )
    if not file_result:
        return None
    file_body, file_headers = file_result
    if _dropfiles_body_looks_like_file(file_headers, file_body) and _is_pdf_content(
        file_body
    ):
        dest.write_bytes(file_body)
        return pdf_url, "pdf"
    return None


def _extract_wp_upload_images(html: str, year: int, month: int, base_url: str) -> list[str]:
    """Full-size (non-thumbnail) image URLs under a specific wp-content/uploads
    /YYYY/MM/ folder, in first-seen order. Skips WordPress's auto-generated
    resized variants (e.g. "9th_1-1024x724.png") to avoid downloading the same
    page multiple times at different resolutions."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _WP_UPLOAD_IMAGE_RE.finditer(html):
        y, mo, name = int(match.group(1)), int(match.group(2)), match.group(3)
        if y != year or mo != month or _RESIZED_IMAGE_SUFFIX_RE.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(urljoin(base_url, f"/wp-content/uploads/{y}/{mo:02d}/{name}"))
    return out


async def _images_bytes_to_pdf(dest: Path, image_bytes_list: list[bytes]) -> None:
    from PIL import Image as PILImage

    pages = [PILImage.open(io.BytesIO(b)).convert("RGB") for b in image_bytes_list]
    if not pages:
        raise RecipeReplayError("No bulletin page images to convert")
    pages[0].save(str(dest), "PDF", save_all=True, append_images=pages[1:])


async def _try_waf_retry_wordpress_bulletin(
    listing_url: str,
    dest: Path,
    *,
    post_slug_patterns: list[str],
    target_date: date,
    example_post_url: str | None = None,
    weeks_back: int = 8,
) -> tuple[str, str] | None:
    """Discover + download a WordPress bulletin post on a WAF-flaky host by
    scraping raw HTML fetched via plain-HTTP retries — never via Playwright
    navigation. Built for stgerardsparish.org (single embedded page image per
    post) and stpatricksbelfast.org (PDF Embedder plugin iframe per post),
    both on the same SiteGround-hosted infra as threepatrons.org /
    stmarysportglenone.org (see _DROPFILES_HTTP_* comment) — a probabilistic
    'sg-captcha' challenge that plain HTTP retries get through in a handful
    of attempts far more reliably than a full browser navigation.

    1. Fetch the listing page (homepage or category archive).
    2. Find post links matching *post_slug_patterns*, score by date extracted
       from the URL, and pick the newest (this is a genuine scrape of the
       site's real current post, not a guess — some of these parishes don't
       post every single week, so guessing a slug/number would be wrong as
       often as it's right).
    3. If the listing is empty or WAF-blocked, optionally predict dated post
       URLs from *example_post_url* (Holywood
       ``/bulletins/bulletin-notice-sunday-{Dth}-{month}-{YYYY}/``). 404s
       are a hard miss — never invent a Sunday that does not exist.
    4. Fetch that post page and pull out either a PDF Embedder iframe's
       target PDF, or the post's own (non-thumbnail) uploaded page image(s).
    5. Fetch the actual file(s) and save/convert to *dest* as a PDF.

    Every stage runs off a single shared time budget (_WAF_RETRY_OVERALL_BUDGET_S)
    rather than a fixed budget per stage — a multi-page image bulletin can need
    several separate file fetches after the listing+post fetches already ran,
    and each stage must shrink to fit whatever's left so the whole function
    still finishes comfortably inside a recipe's total_timeout_s.
    """
    started = time.monotonic()

    def _remaining_budget(safety_margin_s: float = 5.0) -> float:
        return _WAF_RETRY_OVERALL_BUDGET_S - (time.monotonic() - started) - safety_margin_s

    def _stage_budget(preferred_s: float) -> float:
        return max(1.0, min(preferred_s, _remaining_budget()))

    listing_html = ""
    if _remaining_budget() > 0:
        listing_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            listing_url,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_stage_budget(_DROPFILES_HTTP_LISTING_BUDGET_S),
        )
        if listing_result:
            listing_body, listing_headers = listing_result
            if "text/html" in (listing_headers.get("content-type") or "").lower():
                listing_html = listing_body.decode("utf-8", errors="ignore")

    post_urls: list[str] = []

    def _remember_post(url: str) -> None:
        url = (url or "").strip()
        if url and url not in post_urls:
            post_urls.append(url)

    candidates = _extract_matching_hrefs(listing_html, listing_url, post_slug_patterns)
    scored = _score_wordpress_post_hrefs(candidates, target_date)
    if scored:
        _remember_post(max(scored)[1])
    # Holywood (and similar): listing can be stale or WAF-empty. Predict
    # /bulletin-notice-sunday-{Dth}-{month}-{YYYY}/ and skip 404s — never
    # invent a Sunday that does not exist.
    if example_post_url:
        for url in predicted_dated_upload_urls(
            example_post_url, target_date, weeks_back=weeks_back
        ):
            _remember_post(url)
    if not post_urls:
        return None

    for post_url in post_urls:
        if _remaining_budget() <= 0:
            break
        post_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            post_url,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_stage_budget(_DROPFILES_HTTP_FILE_BUDGET_S),
        )
        if not post_result:
            continue
        post_body, post_headers = post_result
        post_ct = (post_headers.get("content-type") or "").lower()
        # Loughshore (and similar) 302 the Sunday post straight to the PDF.
        if _is_pdf_content(post_body) or (
            _dropfiles_body_looks_like_file(post_headers, post_body)
            and _is_pdf_content(post_body)
        ):
            dest.write_bytes(post_body)
            return post_url, "pdf"
        if "text/html" not in post_ct:
            continue
        post_html = post_body.decode("utf-8", errors="ignore")

        if _remaining_budget() > 0:
            found = await _download_pdfembed_from_html(
                post_html,
                post_url,
                dest,
                max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                total_budget_s=_stage_budget(_DROPFILES_HTTP_FILE_BUDGET_S),
            )
            if found:
                return found

        post_date = extract_date_from_slug(post_url) or extract_date_from_string(post_url)
        if post_date is None and scored:
            post_date = max(scored)[0]
        if post_date is None:
            continue
        image_urls = _extract_wp_upload_images(
            post_html, post_date.year, post_date.month, post_url
        )
        if not image_urls:
            continue
        image_bytes: list[bytes] = []
        for image_url in image_urls[:6]:
            if _remaining_budget() <= 0:
                break
            image_result = await asyncio.to_thread(
                _fetch_bytes_with_retries,
                image_url,
                max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                total_budget_s=_stage_budget(_DROPFILES_HTTP_FILE_BUDGET_S),
            )
            if not image_result:
                continue
            image_body, image_headers = image_result
            if _dropfiles_body_looks_like_file(image_headers, image_body):
                image_bytes.append(image_body)
        if image_bytes:
            await _images_bytes_to_pdf(dest, image_bytes)
            return post_url, "image_to_pdf"

    return None


# naomhfionan.com (Falcarragh, Raphoe): the HTML listing page (/nuachtlitir/)
# sits behind a genuine Cloudflare Managed Challenge that blocks every browser
# attempt (headless AND headful) — but the actual bulletin PDFs live on the
# site's wp-content/uploads asset path, which is NOT challenged at all (plain
# HTTP GETs to a known filename return 200 immediately, confirmed 2026-08-10).
# The filename itself follows a predictable, non-date-only pattern
# (Parish-Newsletter-{N}-for-Sun-{A/B/C}-{DDMMYYYY}.pdf) reverse-engineered
# from ~50 real historical filenames pulled from the Wayback Machine CDX
# index — see naomhfionan_bulletin_url()/naomhfionan_newsletter_number() in
# utils.py and liturgical_cycle_letter() in liturgical.py for the derivation
# and its 2024-2026 verification. A small handful of HTTP retries plus a
# +-1 number fallback (for the rare skipped-week numbering seen in older
# filenames) is enough — no browser, no challenge to solve.
_NAOMHFIONAN_HTTP_ATTEMPTS = 8
_NAOMHFIONAN_HTTP_PER_ATTEMPT_TIMEOUT_S = 10.0
_NAOMHFIONAN_HTTP_BUDGET_PER_CANDIDATE_S = 25.0


async def _try_naomhfionan_predicted_pdf(
    dest: Path,
    target_date: date,
) -> tuple[str, str] | None:
    """Predict + fetch naomhfionan.com's bulletin PDF straight from its
    unprotected wp-content/uploads path, skipping the Cloudflare-challenged
    listing page entirely. See module comment above for why this is safe."""
    from .utils import naomhfionan_bulletin_url

    for offset in (0, -1, 1):
        url = naomhfionan_bulletin_url(target_date, number_offset=offset)
        result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            url,
            max_attempts=_NAOMHFIONAN_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_NAOMHFIONAN_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_NAOMHFIONAN_HTTP_BUDGET_PER_CANDIDATE_S,
        )
        if not result:
            continue
        body, _headers = result
        if _is_pdf_content(body):
            dest.write_bytes(body)
            return url, "pdf"
    return None


async def _try_joomla_dropfiles_click_download(
    page: Page,
    dest: Path,
    timeout_ms: int,
    *,
    target_date: date | None = None,
    example_href: str | None = None,
    allow_prediction: bool = True,
) -> tuple[str, str] | None:
    """
    Resilient Joomla Dropfiles discovery chain:

    1. Primary — ``.mod_dropfiles_latest`` first bulletin link
    2. Fallback 1 — highest visible ``/Bulletins|Newsletters|Weekly-Bulletins/NNN/`` file ID
    3. Fallback 2 — newest by date/keyword scoring among visible download links
    4. Fallback 3 — liturgical-title + sequential ID URL prediction
    """
    # Primary: latest module, first link (newest appears first).
    primary = page.locator(".mod_dropfiles_latest a.mod_downloadlink[href]").first
    picked = await _click_dropfiles_locator_download(page, primary, dest, timeout_ms)
    if picked:
        return picked

    # Collect all visible Dropfiles download anchors once.
    entries = await _collect_anchor_entries(page, "a.mod_downloadlink[href]")
    if entries:
        # Fallback 1: highest sequential file ID.
        id_ranks: list[tuple[int, int, int]] = []
        for ent in entries:
            resolved = urljoin(page.url, ent["href"])
            if resolved and _is_non_bulletin_url(resolved):
                continue
            m = _DROPFILES_FILE_ID_RE.search(resolved)
            if not m:
                continue
            file_id = int(m.group(1))
            id_ranks.append((file_id, -ent["idx"], ent["idx"]))
        if id_ranks:
            best_idx = max(id_ranks)[2]
            picked = await _click_dropfiles_locator_download(
                page, page.locator("a.mod_downloadlink[href]").nth(best_idx), dest, timeout_ms
            )
            if picked:
                return picked

        # Fallback 2: date / keyword scoring.
        scored_idx = _best_scored_link_index(entries, page.url, position="top")
        if scored_idx is not None:
            picked = await _click_dropfiles_locator_download(
                page,
                page.locator("a.mod_downloadlink[href]").nth(scored_idx),
                dest,
                timeout_ms,
            )
            if picked:
                return picked

        # Last visible-link attempt: selector order (list module, then any).
        for selector in DROPFILES_DOWNLOAD_SELECTORS[1:]:
            picked = await _click_dropfiles_locator_download(
                page, page.locator(selector).first, dest, timeout_ms
            )
            if picked:
                return picked

    if not allow_prediction:
        return None

    # Fallback 3: predict URL when listing is missing/blocked.
    return await _try_dropfiles_predicted_downloads(
        page,
        dest,
        example_href or "",
        timeout_ms,
        target_date=target_date,
    )


async def _try_browser_nav_download(
    page: Page,
    dest: Path,
    raw_url: str,
    timeout_ms: int,
) -> tuple[str, str] | None:
    """Navigate in a real browser tab — required when bare HTTP gets 403."""
    url = (raw_url or "").strip()
    if not url:
        return None

    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            response = await page.goto(url, timeout=timeout_ms, wait_until="commit")
        download = await dl_info.value
        file_type = await _save_download_to_pdf(download, dest)
        return url, file_type
    except Exception:
        pass

    response = None
    try:
        response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except Exception:
        return None

    if response is not None:
        try:
            body = await response.body()
            if _is_pdf_content(body):
                dest.write_bytes(body)
                return url, "pdf"
        except Exception:
            pass

    picked = await _try_joomla_dropfiles_click_download(
        page, dest, timeout_ms, allow_prediction=False
    )
    if picked:
        return picked

    if _is_document_url(page.url):
        try:
            return await _download_document_url(page, page.url, dest)
        except RecipeReplayError:
            pass

    return None


def _resolve_download_candidates(
    step_url: str,
    *,
    target_date: date | None,
    use_captured_url: bool = False,
    use_target_url: bool = False,
) -> list[str]:
    step_url = (step_url or "").strip()
    if not step_url:
        return []
    # Parish Press Uploader parishes serve a single current file named
    # exactly "bulletin.<ext>" — the parish might upload a PDF one week and a
    # Word doc or a bare photo the next (see harvester.utils for details), so
    # always try every supported extension regardless of use_captured_url.
    uploader_candidates = parish_uploader_bulletin_candidates(step_url)
    if uploader_candidates:
        return uploader_candidates
    # Permanent / ParishPress paths must not be date-rewritten into 404 guesses.
    if use_captured_url or use_target_url or looks_like_permanent_bulletin_url(step_url) or not target_date:
        return [step_url]
    if "newsletter" in step_url.lower() and "onewebmedia" in step_url.lower():
        return oneweb_newsletter_download_urls(step_url, target_date)
    if re.search(r"/(?:Newsletters|Weekly-Bulletins|Bulletins)/\d+/", step_url, re.I):
        predicted = predict_dropfiles_bulletin_urls(step_url, target_date)
        rewritten = rewrite_newsletter_number_for_target(step_url, target_date)
        out: list[str] = []
        for url in [*predicted, rewritten, step_url]:
            if url and url not in out:
                out.append(url)
        return out
    return [rewrite_date_url(step_url, target_date)]


async def _try_download_page_url(
    page: Page,
    dest: Path,
    raw_url: str | None = None,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str] | None:
    """Download a URL that serves PDF bytes without a .pdf suffix (e.g. cappaghparish.com/b/2)."""
    url = (raw_url or page.url or "").strip()
    if not url or url.startswith(("about:", "chrome:", "blob:", "data:")):
        return None
    try:
        return await _download_document_url(page, url, dest, timeout_ms=timeout_ms)
    except RecipeReplayError:
        pass
    if _is_gdrive_usercontent_url(url):
        return None
    return await _try_browser_nav_download(page, dest, url, timeout_ms)


def _fit_image_to_a4_page(image):
    from PIL import Image  # type: ignore[import]

    page_width = 1240
    page_height = 1754
    source = image.convert("RGB")
    scale = min(page_width / source.width, page_height / source.height)
    scaled = source.resize(
        (
            max(1, int(round(source.width * scale))),
            max(1, int(round(source.height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (page_width, page_height), (255, 255, 255))
    offset = ((page_width - scaled.width) // 2, (page_height - scaled.height) // 2)
    canvas.paste(scaled, offset)
    return canvas


async def _download_image_bytes(
    page: Page, raw_url: str, timeout_ms: int = PAGE_LOAD_TIMEOUT_MS
) -> bytes:
    response = await page.request.get(raw_url, timeout=timeout_ms)
    if not response.ok:
        raise RecipeReplayError(f"HTTP {response.status} for {raw_url}")
    return await response.body()


async def _download_image_url_as_pdf(page: Page, raw_url: str, dest: Path) -> tuple[str, str]:
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise RecipeReplayError(
            "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
        ) from exc
    try:
        body = await _download_image_bytes(page, raw_url)
        img = Image.open(io.BytesIO(body)).convert("RGB")
        img.save(str(dest), "PDF")
    except RecipeReplayError:
        raise
    except Exception as exc:
        raise RecipeReplayError(f"Invalid image content for bulletin conversion: {raw_url}") from exc
    return raw_url, "image_to_pdf"


async def _download_image_urls_as_pdf(
    page: Page,
    image_urls: list[str],
    dest: Path,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str]:
    if not image_urls:
        raise RecipeReplayError("Recipe image_stack step found no bulletin image URLs")
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise RecipeReplayError(
            "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
        ) from exc

    pages = []
    for raw_url in image_urls:
        try:
            body = await _download_image_bytes(page, raw_url, timeout_ms=timeout_ms)
            with Image.open(io.BytesIO(body)) as img:
                pages.append(_fit_image_to_a4_page(img))
        except RecipeReplayError:
            raise
        except Exception as exc:
            raise RecipeReplayError(
                f"Invalid image content for bulletin conversion: {raw_url}"
            ) from exc

    if not pages:
        raise RecipeReplayError("Recipe image_stack step found no usable bulletin images")

    pages[0].save(
        str(dest),
        save_all=True,
        append_images=pages[1:],
        format="PDF",
        resolution=150,
    )
    return image_urls[0], "image_to_pdf"


async def _find_stacked_bulletin_image_urls(
    page: Page,
    count: int,
    *,
    selector: str = "",
    min_long_side: int = 550,
    min_short_side: int = 500,
    position: str = "first",
) -> list[str]:
    """Return *count* large bulletin images on the page in DOM order.

    Defaults accept A4-ish page scans (~595×841) while still excluding small
    logos/icons. position: "first" (default) or "last" — Wix homepages often
    archive old bulletin JPEGs above the current week; use "last" to grab the
    newest pair.
    """
    if count < 1:
        return []

    eval_selector = selector.strip() or "img"
    raw_images = await page.eval_on_selector_all(
        eval_selector,
        """
        (els) => els.map((el, index) => {
            const src =
              el.currentSrc ||
              el.getAttribute('src') ||
              el.getAttribute('data-src') ||
              el.getAttribute('data-lazy-src') ||
              el.getAttribute('data-original') ||
              '';
            // Lazy-loaded images report naturalWidth/Height as 0 until the
            // browser has decoded them. Fall back to the rendered box size or
            // explicit width/height attributes so a not-yet-loaded bulletin
            // image isn't dropped as "too small".
            let width = Number(el.naturalWidth || 0);
            let height = Number(el.naturalHeight || 0);
            if (!width || !height) {
              width = width || el.offsetWidth || Number(el.getAttribute('width') || 0);
              height = height || el.offsetHeight || Number(el.getAttribute('height') || 0);
            }
            return {
              index,
              src,
              naturalWidth: width,
              naturalHeight: height,
            };
        })
        """,
    )

    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in raw_images:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src", "")).strip()
        if not src or src.startswith("data:"):
            continue
        resolved = urljoin(page.url, src)
        lower = resolved.lower()
        if lower in seen or lower.endswith(".svg") or "image/svg+xml" in lower:
            continue
        width = int(item.get("naturalWidth") or 0)
        height = int(item.get("naturalHeight") or 0)
        long_side = max(width, height)
        short_side = min(width, height)
        if long_side < min_long_side or short_side < min_short_side:
            continue
        seen.add(lower)
        candidates.append((int(item.get("index") or 0), resolved))

    candidates.sort(key=lambda item: item[0])
    pick = str(position or "first").strip().lower()
    if pick == "last":
        return [url for _idx, url in candidates[-count:]]
    return [url for _idx, url in candidates[:count]]


async def _print_page_to_pdf(page: Page, dest: Path) -> None:
    pdf_bytes = await page.pdf(
        format="A4",
        print_background=True,
        margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
    )
    dest.write_bytes(pdf_bytes)


def _verify_bulletin_pdf(dest: Path, max_pages: int | None = None) -> None:
    """Reject HTML/print captures that are too long to be a real weekly bulletin.

    Mirrors ``fetcher._verify_bulletin_pdf`` so recipe-driven HTML/print_to_pdf
    steps get the same page-count safety net as direct PDF downloads (previously
    only the direct-download path was checked; the HTML print fallback below
    could silently save a full multi-page article/site as the "bulletin").

    *max_pages* lets a recipe override the global default via its own
    ``max_bulletin_pages`` field (e.g. multi-parish pastoral-area newsletters
    that are genuinely longer than a normal single-parish bulletin).
    """
    limit = MAX_BULLETIN_PAGES if max_pages is None else int(max_pages)
    try:
        reader = PdfReader(str(dest))
        page_count = len(reader.pages)
    except Exception:
        return  # unreadable — leave it to the caller's PDF checks
    if page_count > limit:
        dest.unlink(missing_ok=True)
        raise ValueError(
            f"❌ Too many pages: {page_count} pages (max {limit})"
        )


async def _smart_print_page_to_pdf(
    page: Page,
    dest: Path,
    target: date,
    *,
    wait_ms: int = 2500,
    skip_listing_nav: bool = False,
    max_pages: int | None = None,
) -> None:
    """Print HTML bulletins using Parish Messenger / content-region detection when possible."""
    from .html_capture import capture_html_page_as_pdf

    def _verify(d: Path) -> None:
        _verify_bulletin_pdf(d, max_pages)

    ok, _mode = await capture_html_page_as_pdf(
        page,
        dest,
        target,
        print_pdf=_print_page_to_pdf,
        verify_pdf=_verify,
        wait_ms=wait_ms,
        skip_listing_nav=skip_listing_nav,
    )
    if not ok:
        await _print_page_to_pdf(page, dest)
        _verify_bulletin_pdf(dest, max_pages)


def _recipe_uses_parish_messenger(recipe: dict) -> bool:
    site = str(recipe.get("site_type") or recipe.get("playbook_type") or "").lower()
    return "parish_messenger" in site or site == "parish_messenger"


async def _prepare_page_for_html_print(
    page: Page, recipe: dict, step_timeout_ms: int
) -> None:
    """Wait for bulletin HTML before print_to_pdf — messenger widgets never reach networkidle."""
    from .html_capture import wait_for_dynamic_bulletin

    if _recipe_uses_parish_messenger(recipe):
        await wait_for_dynamic_bulletin(
            page, timeout_ms=min(max(step_timeout_ms, 20_000), 90_000)
        )
        await asyncio.sleep(2.0)
        return
    try:
        await page.wait_for_load_state(
            "networkidle", timeout=min(step_timeout_ms, 15_000)
        )
    except PlaywrightTimeoutError:
        pass
    await asyncio.sleep(2.5)


async def _find_pdfemb_url(page: Page, target_date: date | None = None) -> str | None:
    """Best PDF Embedder bulletin URL on the page.

    Newer PDF Embedder builds render canvases without ``a.pdfemb-viewer[href]``.
    Fall back to network-loaded ``*.pdf`` resources (and any leftover hrefs).
    """
    # Give lazy network PDF fetches a moment to appear in performance entries.
    for _ in range(10):
        links = await page.eval_on_selector_all(PDFEMB_SELECTOR, PDFEMB_HREF_EXTRACT_JS)
        try:
            network_pdfs = await page.evaluate(
                """() => performance.getEntriesByType('resource')
                    .map(r => r.name)
                    .filter(n => /\\.pdf($|\\?)/i.test(n))"""
            )
        except Exception:
            network_pdfs = []
        if not isinstance(network_pdfs, list):
            network_pdfs = []

        candidates: list[str] = []
        for href in [*links, *network_pdfs]:
            if not isinstance(href, str) or not href.strip():
                continue
            resolved = urljoin(page.url, href.strip())
            lower = resolved.lower()
            if not (lower.endswith(".pdf") or ".pdf" in lower):
                continue
            if _is_non_bulletin_url(resolved):
                continue
            candidates.append(resolved)
        if candidates:
            week_start = (target_date - timedelta(days=6)) if target_date else None

            def _rank(item: tuple[int, str]) -> tuple:
                idx, url = item
                date_score, keyword_bonus = _score_bulletin_url(url)
                freshness = 0
                if target_date is not None:
                    extracted = extract_date_from_string(unquote(url))
                    if extracted and week_start is not None and week_start <= extracted <= target_date:
                        freshness = 2
                    elif extracted and extracted > target_date:
                        freshness = 1
                return (freshness, date_score, keyword_bonus, -idx)

            ranked = sorted(enumerate(candidates), key=_rank, reverse=True)
            return ranked[0][1]
        await asyncio.sleep(0.5)
    return None


async def _find_iframe_pdf_url(page: Page) -> str | None:
    """Return the best embedded PDF URL (iframe, object, or embed)."""
    srcs = await page.eval_on_selector_all(
        "iframe[src], object[data], embed[src]",
        "(els) => els.map(el => el.getAttribute('src') || el.getAttribute('data') || '').filter(Boolean)",
    )
    candidates: list[str] = []
    for src in srcs:
        if not isinstance(src, str) or not src.strip():
            continue
        resolved = urljoin(page.url, src.strip())
        unwrapped = unwrap_docs_viewer_url(resolved)
        pick = unwrapped if unwrapped != resolved else resolved
        lower = pick.lower()
        if ".pdf" not in lower:
            continue
        if _is_non_bulletin_url(pick):
            continue
        candidates.append(pick)
    if not candidates:
        return None
    candidates.sort(
        key=lambda u: (_score_bulletin_url(u)[0], _score_bulletin_url(u)[1]),
        reverse=True,
    )
    return candidates[0]


async def _click_locator_match(
    page: Page,
    locator,
    step_timeout_ms: int,
) -> None:
    href = ((await locator.get_attribute("href")) or "").strip()
    resolved = urljoin(page.url, href) if href else ""
    before = page.url
    try:
        await locator.wait_for(state="visible", timeout=step_timeout_ms)
        await locator.click(timeout=step_timeout_ms)
    except PlaywrightTimeoutError:
        if resolved and _looks_like_http_url(resolved):
            try:
                await _navigate_page(page, resolved, step_timeout_ms, wait_until="commit")
            except PlaywrightError as exc:
                if "ERR_ABORTED" not in str(exc):
                    raise
                # Chromium aborts goto() when the target is a direct file
                # download (e.g. a bulletin PDF the browser hands off to a
                # download instead of rendering) — this is expected, not a
                # broken selector. Without this, every parish whose newest
                # bulletin link happens to be a direct PDF (not a listing
                # page) was misreported as "recipe outdated" here even
                # though the correct link was found (see annagryparish).
                return
        else:
            raise
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=POST_CLICK_WAIT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass

    # Some WP themes "accept" the click without leaving the listing page.
    # If we have a real article href and the URL did not change, navigate directly.
    if resolved and _looks_like_http_url(resolved):
        before_path = urlparse(before).path.rstrip("/")
        after_path = urlparse(page.url).path.rstrip("/")
        target_path = urlparse(resolved).path.rstrip("/")
        if after_path == before_path and target_path and target_path != before_path:
            try:
                await _navigate_page(page, resolved, step_timeout_ms, wait_until="commit")
            except PlaywrightError as exc:
                if "ERR_ABORTED" not in str(exc):
                    raise
                # Chromium aborts goto() when the target is a file download —
                # the original click already triggered it (see page.on("download")
                # listener in replay_recipe); nothing to navigate to, so stop here
                # instead of surfacing this as "Recipe outdated".
                return
            try:
                await page.wait_for_load_state(
                    "domcontentloaded", timeout=POST_CLICK_WAIT_TIMEOUT_MS
                )
            except PlaywrightTimeoutError:
                pass


def _peek_next_download_step(steps: list, index: int) -> dict | None:
    """Return the next download step if click steps can be skipped."""
    for step in steps[index + 1 :]:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip().lower()
        if action == "download":
            return step
        if action != "click":
            break
    return None


_NO_PDF_PROBE_ACTIONS = {
    "image",
    "image_stack",
    "print_to_pdf",
    "html",
    "crop_screenshot",
}


_PDF_LIKE_SELECTOR_RE = re.compile(
    r"pdfemb|mdocs|dropfile|wp-block-file|href\s*[*$^]?=[^)]*pdf", re.IGNORECASE
)


def _next_step_skips_pdf_probe(steps: list, index: int, recipe: dict | None = None) -> bool:
    """True when the step right after this ``goto`` doesn't need a PDF link.

    ``_wait_for_bulletin_content`` only ever waits for PDF-shaped selectors
    (mdocs tables, pdfemb viewers, ``a[href$='.pdf']``, ...). Recipes whose
    next step is ``image``/``image_stack`` (a bare full-page scan ``<img>``,
    no PDF link at all — e.g. derriaghycatholicparish) or
    ``print_to_pdf``/``html``/``crop_screenshot`` (which print the page's own
    HTML and run their own dedicated wait via ``_prepare_page_for_html_print``,
    including parish_messenger-specific handling) never satisfy any of those
    probes, so this wait always burns its full budget (up to 240s) doing
    nothing useful before the real step's own wait logic runs anyway (found
    2026-08-09: derriaghycatholicparish and parishofardstraweast both timed
    out here despite their actual capture step succeeding in seconds once
    reached).

    Also skip when the next step is a ``click`` on a selector that plainly
    isn't PDF-shaped (e.g. picking a dated "...Newsletter" link by text) and
    the recipe hasn't opted into one of the PDF-widget playbooks that the
    probe's non-default selector lists target — same wasted-budget issue,
    just one step later (found 2026-08-09, parishofardstraweast: the click
    target is a plain dated link, not a PDF, so the probe list is
    irrelevant, yet it still burned the full timeout before the click ran).
    """
    for step in steps[index + 1 :]:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip().lower()
        if action in _NO_PDF_PROBE_ACTIONS:
            return True
        if action == "click":
            if is_cloud_folder_click_step(step):
                return True
            playbook = str((recipe or {}).get("playbook_type") or (recipe or {}).get("site_type") or "")
            if any(tag in playbook.lower() for tag in ("pdfemb", "mdocs", "wp_block", "permanent_bulletin", "mcn_live", "mcn_pdf", "churchmedia")):
                return False
            selector = str(step.get("selector") or "")
            return not _PDF_LIKE_SELECTOR_RE.search(selector)
        return False
    return False


_ANCHOR_BATCH_JS = """
(els) => els.map((el, idx) => ({
  href: el.href || el.getAttribute('href') || '',
  text: ((el.innerText || el.textContent || '') + '').trim().slice(0, 300),
  idx: idx
})).filter(x => x.href)
"""


async def _collect_anchor_entries(page: Page, selector: str) -> list[dict]:
    """Read href + label for all matching anchors in one browser round-trip."""
    try:
        raw = await page.eval_on_selector_all(selector, _ANCHOR_BATCH_JS)
    except Exception:
        return []
    entries: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        if not href:
            continue
        entries.append(
            {
                "href": href,
                "text": str(item.get("text") or ""),
                "idx": int(item.get("idx") or 0),
            }
        )
    return entries


def _best_newsletter_link_index(
    entries: list[dict],
    page_url: str,
    *,
    position: str = "top",
    href_patterns: list[str] | None = None,
    href_skip: list[str] | None = None,
) -> int | None:
    """Pattern H: pick highest /Newsletters/NNN/, /Weekly-Bulletins/NNN/, or /Bulletins/NNN/ number."""
    ranks: list[tuple[int, int, int]] = []
    for ent in entries:
        resolved = urljoin(page_url, ent["href"])
        if not _href_allowed_for_click(resolved, href_patterns, href_skip):
            continue
        num = extract_newsletter_number(resolved)
        if num is None:
            continue
        tiebreak = ent["idx"] if position == "bottom" else -ent["idx"]
        ranks.append((num, tiebreak, ent["idx"]))
    if not ranks:
        return None
    return max(ranks)[2]


def _best_scored_link_index(
    entries: list[dict],
    page_url: str,
    *,
    position: str = "top",
    href_patterns: list[str] | None = None,
    href_skip: list[str] | None = None,
) -> int | None:
    best_idx: int | None = None
    best_rank: tuple[int, int] = (-1, -1)
    for ent in entries:
        resolved = urljoin(page_url, ent["href"])
        if not _href_allowed_for_click(resolved, href_patterns, href_skip):
            continue
        total, _date_score, _keyword = _score_bulletin_link(resolved, ent["text"])
        tiebreak = ent["idx"] if position == "bottom" else -ent["idx"]
        rank = (total, tiebreak)
        if rank > best_rank:
            best_rank = rank
            best_idx = ent["idx"]
    return best_idx


async def _replay_click_by_strategy(
    page: Page,
    step: dict,
    selectors: list[str],
    step_timeout_ms: int,
    *,
    href_patterns: list[str] | None = None,
    href_skip: list[str] | None = None,
) -> bool:
    """Click the best bulletin link when pick_strategy is set. Returns True on success."""
    strategy = (step.get("pick_strategy") or "").strip().lower()
    if strategy not in {"newest_dated", "first_match", "last_match"}:
        return False

    position = (step.get("bulletin_position") or "top").strip().lower()
    errors: list[str] = []

    for sel in selectors:
        try:
            entries = await _collect_anchor_entries(page, sel)
            if not entries:
                continue

            locator = page.locator(sel)
            safe_entries = [
                ent
                for ent in entries
                if _href_allowed_for_click(
                    urljoin(page.url, ent["href"]), href_patterns, href_skip
                )
            ]
            if not safe_entries:
                errors.append(
                    f"{sel}: only non-bulletin links matched (GDPR/Safeguarding/"
                    "Privacy/DataEntry/New Parishioner etc.) — no genuine bulletin link found"
                )
                continue

            if strategy == "first_match":
                await _click_locator_match(
                    page, locator.nth(safe_entries[0]["idx"]), step_timeout_ms
                )
                return True
            if strategy == "last_match":
                await _click_locator_match(
                    page, locator.nth(safe_entries[-1]["idx"]), step_timeout_ms
                )
                return True

            newsletter_idx = _best_newsletter_link_index(
                entries,
                page.url,
                position=position,
                href_patterns=href_patterns,
                href_skip=href_skip,
            )
            if newsletter_idx is not None:
                await _click_locator_match(page, locator.nth(newsletter_idx), step_timeout_ms)
                return True

            best_idx = _best_scored_link_index(
                entries,
                page.url,
                position=position,
                href_patterns=href_patterns,
                href_skip=href_skip,
            )
            if best_idx is not None:
                await _click_locator_match(page, locator.nth(best_idx), step_timeout_ms)
                return True

            fallback_idx = safe_entries[-1]["idx"] if position == "bottom" else safe_entries[0]["idx"]
            await _click_locator_match(page, locator.nth(fallback_idx), step_timeout_ms)
            return True
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    if errors:
        raise RecipeReplayError("; ".join(errors[:MAX_SELECTOR_ERRORS]))
    return False


async def _drive_folder_rows(page: Page) -> list[dict]:
    try:
        rows = await page.evaluate(
            """() => Array.from(document.querySelectorAll('[role="row"]')).map((row) => ({
              text: ((row.innerText || row.textContent || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 300),
              id: row.getAttribute('data-id')
            }))"""
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "text": str(row.get("text") or ""),
                "id": str(row.get("id") or "").strip(),
            }
        )
    return out


async def _open_drive_year_folder(page: Page, year: int, timeout_ms: int) -> None:
    """Open the year-named subfolder by Drive data-id (no brittle UI clicks)."""
    year_label = str(year)
    folder_id = None
    # Drive folder listings hydrate after first paint — retry briefly.
    deadline = asyncio.get_event_loop().time() + min(max(timeout_ms / 1000, 5), 45)
    while folder_id is None and asyncio.get_event_loop().time() < deadline:
        for row in await _drive_folder_rows(page):
            text = (row.get("text") or "").strip()
            if not text.startswith(year_label):
                continue
            # Accept "2026 …"; reject longer numeric tokens like "20260".
            if len(text) > len(year_label) and text[len(year_label)].isdigit():
                continue
            folder_id = row.get("id") or None
            if folder_id:
                break
        if folder_id:
            break
        await page.wait_for_timeout(500)
    if not folder_id:
        raise RecipeReplayError(
            f"Cloud year folder {year_label} not found on Drive listing — "
            "check the parent folder URL / sharing"
        )
    await page.goto(
        f"https://drive.google.com/drive/folders/{folder_id}",
        timeout=min(timeout_ms, 60_000),
        wait_until="domcontentloaded",
    )
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
    except Exception:
        pass
    await page.wait_for_timeout(1500)
    if f"/folders/{folder_id}" not in (page.url or ""):
        raise RecipeReplayError(
            f"Failed to open Drive year folder {year_label} ({folder_id})"
        )


async def _selected_drive_row_id(page: Page) -> str | None:
    try:
        file_id = await page.evaluate(
            "() => { const row = document.querySelector('[role=\"row\"][aria-selected=\"true\"]'); "
            "return row ? row.getAttribute('data-id') : null; }"
        )
    except Exception:
        return None
    token = str(file_id or "").strip()
    return token or None


async def _open_selected_drive_row(page: Page, timeout_ms: int) -> None:
    """Open the Drive *file* row just clicked.

    A single click on a Drive folder row only selects/highlights it (sets
    ``aria-selected="true"`` on the ``<tr>``) — it does not navigate
    anywhere and no download fires. Pressing Enter/double-clicking to "open"
    the file inside Drive's own viewer is slow and flaky to automate, but
    the row's ``<tr data-id="...">`` attribute already exposes the file's
    Drive ID directly in the DOM — construct the direct-download URL from it
    and navigate straight there. That either fires a native browser
    "download" event (picked up by the following ``download`` step's
    ``downloads.pop(0)``) or gets abandoned as ERR_ABORTED once Chromium
    hands the response to its download manager, which is expected and
    ignored (see Bruckless: previously the click step "succeeded" but the
    following download step had nothing to find, "did not find a matching
    document URL").
    """
    file_id = await _selected_drive_row_id(page)
    if file_id:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        try:
            await page.goto(download_url, timeout=min(timeout_ms, 30_000))
        except Exception:
            pass
        return
    try:
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 15_000))
    except Exception:
        pass


async def _click_newest_cloud_pdf_row(page: Page, timeout_ms: int) -> bool:
    """Download the Drive row with the newest YY.MM.DD.pdf filename via data-id."""
    rows = await _drive_folder_rows(page)
    if not rows:
        return False
    label = newest_yy_mm_dd_label([row.get("text") or "" for row in rows])
    if not label:
        return False
    file_id = None
    for row in rows:
        if label in (row.get("text") or ""):
            file_id = row.get("id") or None
            if file_id:
                break
    if file_id:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        try:
            await page.goto(download_url, timeout=min(timeout_ms, 30_000))
        except Exception:
            pass
        return True
    try:
        escaped = label.replace("'", "\\'")
        locator = page.locator(f'[role="row"]:has-text("{escaped}")').first
        await _click_locator_match(page, locator, timeout_ms)
        await _open_selected_drive_row(page, timeout_ms)
        return True
    except Exception:
        return False


async def _replay_click(
    page: Page,
    step: dict,
    step_timeout_ms: int,
    *,
    target_date: date | None = None,
    recipe: dict | None = None,
) -> None:
    is_year_folder = is_year_folder_click_step(step)
    is_cloud_folder = is_cloud_folder_click_step(step)
    pick_strategy = (step.get("pick_strategy") or "").strip().lower()
    prefer_newest_cloud = is_cloud_folder and pick_strategy == "newest_dated"

    if target_date:
        if is_year_folder:
            step = rewrite_year_folder_click_step(step, target_date)
        elif is_cloud_folder and not prefer_newest_cloud:
            step = rewrite_cloud_folder_click_step(step, target_date)
            is_cloud_folder = True
        elif is_cloud_folder:
            is_cloud_folder = True

    # Year folders: resolve data-id from the listing and navigate directly.
    # A lone click only highlights the row; Enter/open is flaky in headless Drive.
    if is_year_folder:
        year = target_date.year if target_date else int(str(step.get("text") or "0") or 0)
        if year < 2000:
            raise RecipeReplayError("Cloud year folder click missing target year")
        await _open_drive_year_folder(page, year, step_timeout_ms)
        return

    selectors: list[str] = []
    selector = (step.get("selector") or "").strip()
    if selector:
        selectors.append(selector)
    selectors.extend(
        s.strip() for s in step.get("fallback_selectors", []) if isinstance(s, str) and s.strip()
    )

    if not selectors:
        raise RecipeReplayError("Recipe click step missing selector")

    # Drive folder listings are role=row grids, not <a href> lists — the
    # generic newest_dated anchor scorer cannot see them.
    if prefer_newest_cloud:
        if await _click_newest_cloud_pdf_row(page, step_timeout_ms):
            return
        if target_date:
            step = rewrite_cloud_folder_click_step(step, target_date)
            selectors = [(step.get("selector") or "").strip()]
            selectors.extend(
                s.strip()
                for s in step.get("fallback_selectors", [])
                if isinstance(s, str) and s.strip()
            )
            selectors = [s for s in selectors if s]

    href_patterns, href_skip = _click_href_filters(step, recipe)

    if step.get("pick_strategy") and not is_cloud_folder and not is_year_folder:
        if await _replay_click_by_strategy(
            page,
            step,
            selectors,
            step_timeout_ms,
            href_patterns=href_patterns,
            href_skip=href_skip,
        ):
            return

    errors: list[str] = []
    for sel in selectors:
        try:
            if href_patterns or href_skip:
                entries = await _collect_anchor_entries(page, sel)
                allowed = [
                    ent
                    for ent in entries
                    if _href_allowed_for_click(
                        urljoin(page.url, ent["href"]), href_patterns, href_skip
                    )
                ]
                if not allowed:
                    errors.append(
                        f"{sel}: no href matched recipe href_patterns / skip list"
                    )
                    continue
                await _click_locator_match(
                    page, page.locator(sel).nth(allowed[0]["idx"]), step_timeout_ms
                )
            else:
                await _click_locator_match(page, page.locator(sel).first, step_timeout_ms)
            if is_cloud_folder:
                await _open_selected_drive_row(page, step_timeout_ms)
            return
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    detail = "; ".join(errors[:MAX_SELECTOR_ERRORS]) if errors else "no selector details available"
    raise RecipeReplayError(
        f"Recipe outdated — re-train with --train (all selectors failed: {detail})"
    )


async def replay_recipe(
    recipe_path: Path,
    dest: Path,
    browser: Browser,
    *,
    target_url: str | None = None,
    target_date: date | None = None,
) -> tuple[Path, str, str]:
    recipe = load_recipe(recipe_path)
    step_timeout_ms = _recipe_step_timeout_ms(recipe)
    nav_wait_until = _recipe_navigation_wait_until(recipe)
    steps = recipe["steps"]

    start_url = (recipe.get("start_url") or "").strip()
    if not start_url:
        start_url = (target_url or "").strip()
    host_profile = _host_profile_for_start_url(start_url)
    site_type = str(recipe.get("site_type") or "").strip().lower()
    dropfiles_example = _dropfiles_example_href_from_recipe(recipe)

    # Permanent ParishPress path (Newtown Killea): /bulletin/raphoe/slug/
    # redirects to this week's PDF. Never open /bulletin/ — that 403s bots.
    if site_type == "permanent_redirect_document" or looks_like_permanent_bulletin_url(start_url):
        download_url = start_url
        for step in steps:
            if isinstance(step, dict) and str(step.get("url") or "").strip():
                download_url = str(step.get("url") or "").strip()
                break
        found = await _try_http_document_url(download_url, dest)
        if found:
            return dest, found[1], found[0]
        if site_type == "permanent_redirect_document":
            raise RecipeReplayError(
                f"Permanent bulletin URL {download_url} did not return a PDF/DOCX "
                "(listing page was not opened)"
            )

    # MCN.live camera pages expose the weekly newsletter via JSON, not the
    # webcam. HTTP-first so Send & test does not need Playwright for Glenfin.
    if site_type == "mcn_live_parish_page" or (
        "/camera/" in start_url.lower() and "mcn.live" in start_url.lower()
    ):
        found = await _try_mcn_live_newsletter(start_url, dest)
        if found:
            return dest, found[1], found[0]

    # churchmedia.tv livestream pages expose "View Our Latest Newsletter"
    # only after Angular hydrates. GET /api/getChannelAbout?slug=… returns
    # the current PDF; the path token and ?cb= change every upload.
    if site_type == "churchmedia_newsletter" or (
        "churchmedia.tv" in start_url.lower()
        and "/newsletter/" not in start_url.lower()
    ):
        found = await _try_churchmedia_newsletter(start_url, dest, recipe)
        if found:
            return dest, found[1], found[0]

    # mDocs tables (Portstewart): listing HTML is server-rendered with
    # ?mdocs-file=NNNN download links. HTTP-scrape the newest dated row so
    # we never pin "23rd August 2026" or click the title dropdown (href="#").
    playbook = str(recipe.get("playbook_type") or "").strip().lower()
    if target_date is not None and ("mdocs" in site_type or "mdocs" in playbook):
        found = await _try_http_scrape_mdocs(start_url, dest, target_date)
        if found:
            return dest, found[1], found[0]

    # WAF-flaky WordPress sites (stgerardsparish.org, stpatricksbelfast.org —
    # same SiteGround sg-captcha challenge as the joomla_dropfiles sites
    # below): skip Playwright/the browser entirely and go straight to the
    # plain-HTTP-retry scrape, since a full browser was observed to fail far
    # more often against this specific WAF than a bare urllib request (see
    # _DROPFILES_HTTP_* comment) — no point paying for a browser context here.
    if site_type == "waf_retry_wordpress" and target_date is not None:
        post_slug_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("post_slug_patterns") or [])
            if str(p).strip()
        ] or ["bulletin"]
        example_post_url = str(recipe.get("example_post_url") or "").strip()
        if not example_post_url:
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_url = str(step.get("url") or "").strip()
                if step_url and not _looks_like_direct_document_url(step_url):
                    example_post_url = step_url
                    break
        found = await _try_waf_retry_wordpress_bulletin(
            start_url,
            dest,
            post_slug_patterns=post_slug_patterns,
            target_date=target_date,
            example_post_url=example_post_url or None,
            weeks_back=int(recipe.get("weeks_back") or 8),
        )
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"WAF-flaky site {start_url} — could not fetch listing/post via "
            "plain-HTTP retries within budget (not a permanent block; retry later)"
        )

    # naomhfionan.com (Falcarragh): the listing page is a genuine Cloudflare
    # Managed Challenge (confirmed blocked in both headless AND headful
    # Playwright), but the bulletin PDF itself lives on an unchallenged
    # wp-content/uploads asset path with a predictable filename — skip the
    # browser and the challenged page entirely. See _try_naomhfionan_predicted_pdf.
    if site_type == "naomhfionan_numbered_pdf" and target_date is not None:
        found = await _try_naomhfionan_predicted_pdf(dest, target_date)
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"naomhfionan.com predicted PDF URL(s) for {target_date} did not "
            "resolve to a real PDF (not the listing-page block; retry later "
            "or re-check the number/letter prediction)"
        )

    # Listing page is reachable via plain HTTP but the current PDF lives
    # inside a closed accordion (Playwright visible-wait times out). Scrape
    # the raw HTML for matching PDF hrefs and download the newest dated one.
    if site_type == "http_scrape_newest_pdf" and target_date is not None:
        href_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("href_patterns") or [])
            if str(p).strip()
        ] or ["parish-newsletter", ".pdf"]
        post_slug_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("post_slug_patterns") or [])
            if str(p).strip()
        ]
        found = await _try_http_scrape_newest_pdf(
            start_url,
            dest,
            href_patterns=href_patterns,
            target_date=target_date,
            post_slug_patterns=post_slug_patterns or None,
        )
        if found:
            return dest, found[1], found[0]
        example_url = str(recipe.get("example_url") or "").strip()
        if not example_url:
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_url = str(step.get("url") or "").strip()
                if step_url and _looks_like_direct_document_url(step_url):
                    example_url = step_url
                    break
        playbook = str(recipe.get("playbook_type") or "").strip().lower()
        if example_url and (
            playbook == "oneweb_docx"
            or (
                "onewebmedia" in example_url.lower()
                and "newsletter" in example_url.lower()
            )
        ):
            predicted = await _try_predicted_dated_pdf(
                example_url,
                dest,
                target_date,
                weeks_back=int(recipe.get("weeks_back") or 8),
            )
            if predicted:
                return dest, predicted[1], predicted[0]
        raise RecipeReplayError(
            f"HTTP-scrape listing {start_url} — no dated bulletin PDF matching "
            f"{href_patterns} (not a selector problem; parish may not have posted)"
        )

    # Listing/index is Cloudflare-challenged; dated wp-content/uploads files
    # are not. Predict this Sunday and a few previous Sundays and fetch
    # directly. Never navigate to the challenged HTML page.
    if site_type == "predicted_dated_pdf" and target_date is not None:
        example_url = ""
        for step in steps:
            if isinstance(step, dict) and (step.get("url") or "").strip():
                example_url = str(step.get("url") or "").strip()
                if _looks_like_direct_document_url(example_url):
                    break
        if not example_url:
            example_url = start_url
        weeks_back = int(recipe.get("weeks_back") or 8)
        weeks_ahead = int(recipe.get("weeks_ahead") or 0)
        found = await _try_predicted_dated_pdf(
            example_url,
            dest,
            target_date,
            weeks_back=weeks_back,
            weeks_ahead=weeks_ahead,
        )
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"Predicted dated PDF URL(s) from {example_url} for {target_date} "
            "did not resolve to a real file (listing page was not opened)"
        )

    if site_type == "wp_json_newest_media" and target_date is not None:
        href_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("href_patterns") or [])
            if str(p).strip()
        ] or ["sunday", "bulletin", "newsletter"]
        found = await _try_wp_json_newest_media(
            start_url,
            dest,
            href_patterns=href_patterns,
            target_date=target_date,
        )
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"wp-json media at {start_url} — no dated bulletin PDF matching "
            f"{href_patterns} (listing page was not opened)"
        )

    if site_type == "wp_json_newest_post_images" and target_date is not None:
        slug_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("post_slug_patterns") or [])
            if str(p).strip()
        ] or ["bulletin-for-sunday"]
        image_count = int(recipe.get("image_count") or 2)
        for step in steps:
            if isinstance(step, dict) and step.get("action") == "image_stack":
                try:
                    image_count = int(step.get("count") or image_count)
                except (TypeError, ValueError):
                    pass
                break
        found = await _try_wp_json_newest_post_images(
            start_url,
            dest,
            slug_patterns=slug_patterns,
            target_date=target_date,
            example_post_url=str(recipe.get("example_post_url") or "").strip() or None,
            weeks_back=int(recipe.get("weeks_back") or 3),
            image_count=image_count,
        )
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"wp-json/RSS/predicted post images at {start_url} — no Sunday "
            "bulletin post with enough page images (browser was not opened)"
        )

    if site_type == "http_scrape_newest_images" and target_date is not None:
        href_patterns = [
            str(p).strip().lower()
            for p in (recipe.get("href_patterns") or [])
            if str(p).strip()
        ]
        image_count = int(recipe.get("image_count") or 1)
        for step in steps:
            if isinstance(step, dict) and step.get("action") == "image_stack":
                try:
                    image_count = int(step.get("count") or image_count)
                except (TypeError, ValueError):
                    pass
                break
        found = await _try_http_scrape_newest_images(
            start_url,
            dest,
            href_patterns=href_patterns,
            target_date=target_date,
            count=image_count,
        )
        if found:
            return dest, found[1], found[0]
        raise RecipeReplayError(
            f"HTTP-scrape images {start_url} — no bulletin page images matching "
            f"{href_patterns or ['wp-content/uploads']} (browser was not opened)"
        )

    context_opts: dict = {"accept_downloads": True}
    if host_profile.get("ignore_https_errors"):
        context_opts["ignore_https_errors"] = True
    context = await browser.new_context(**context_opts)
    page = await context.new_page()
    downloads: list = []
    page.on("download", lambda d: downloads.append(d))

    first_action = (steps[0].get("action") if steps else "") or ""

    # Google Drive static bulletins: download via HTTP only — never page.goto usercontent URL.
    if _recipe_is_gdrive_static(recipe):
        drive_url = _gdrive_download_url_from_recipe(recipe)
        if drive_url:
            try:
                source_url, file_type = await _download_document_url(
                    page, drive_url, dest, timeout_ms=step_timeout_ms
                )
                return dest, file_type, source_url
            except RecipeReplayError as exc:
                raise RecipeReplayError(str(exc)) from exc

    if start_url and first_action != "goto":
        if _looks_like_direct_document_url(start_url):
            captured = await _goto_or_download(
                page, dest, start_url, downloads, step_timeout_ms,
                wait_until=nav_wait_until,
            )
            if captured:
                return captured
        elif not _recipe_is_gdrive_static(recipe):
            try:
                await _navigate_page(page, start_url, step_timeout_ms, wait_until=nav_wait_until)
            except RecipeReplayError as exc:
                # Dropfiles sites may block the listing page but still serve predicted downloads.
                if (
                    site_type == "joomla_dropfiles"
                    and "blocking automated access" in str(exc).lower()
                ):
                    predicted = await _try_dropfiles_predicted_downloads(
                        page,
                        dest,
                        dropfiles_example,
                        step_timeout_ms,
                        target_date=target_date,
                    )
                    if predicted:
                        return dest, predicted[1], predicted[0]
                raise
            if _looks_like_http_url(start_url):
                last_http_url = start_url

    try:
        last_http_url = start_url if _looks_like_http_url(start_url) else ""
        for step_index, step in enumerate(steps):
            action = step.get("action")
            if action == "goto":
                url = (step.get("url") or "").strip()
                if step.get("use_target_url") and target_url:
                    url = target_url.strip()
                playbook = str(
                    recipe.get("playbook_type") or recipe.get("site_type") or ""
                ).strip().lower()
                if playbook == "wix_dated_slug" and target_date is not None:
                    resolved = await _try_resolve_wix_dated_slug(
                        [url, str(step.get("url") or ""), start_url],
                        target_date,
                        weeks_back=int(recipe.get("weeks_back") or 3),
                    )
                    if resolved:
                        url = resolved
                if not url:
                    raise RecipeReplayError("Recipe goto step missing URL")
                captured = await _goto_or_download(
                    page, dest, url, downloads, step_timeout_ms,
                    wait_until=nav_wait_until,
                )
                if captured:
                    return captured
                if _looks_like_http_url(url):
                    last_http_url = url
                if not _next_step_skips_pdf_probe(steps, step_index, recipe):
                    await _wait_for_bulletin_content(page, recipe, step_timeout_ms)
                continue

            if action == "click":
                upcoming_download = _peek_next_download_step(steps, step_index)
                if upcoming_download and upcoming_download.get("use_captured_url"):
                    step_url = (upcoming_download.get("url") or "").strip()
                    if step_url:
                        for candidate in _resolve_download_candidates(
                            step_url,
                            target_date=target_date,
                            use_captured_url=True,
                        ):
                            tried = await _try_download_page_url(
                                page, dest, candidate, timeout_ms=step_timeout_ms
                            )
                            if tried:
                                return dest, tried[1], tried[0]
                try:
                    await _replay_click(
                        page,
                        step,
                        step_timeout_ms,
                        target_date=target_date,
                        recipe=recipe,
                    )
                except RecipeReplayError:
                    # joomla_dropfiles sites (threepatrons.org,
                    # stmarysportglenone.org) sit behind a PROBABILISTIC WAF
                    # that sometimes lets the initial goto through with a 200
                    # but serves a challenge page with none of the real
                    # .mod_downloadlink anchors — _replay_click then fails to
                    # find the selector at all and raises before we ever
                    # reach the plain-HTTP-retry fallback below. Swallow that
                    # one specific failure mode here (not for other site
                    # types) and fall through to the same
                    # _try_joomla_dropfiles_click_download fallback chain
                    # used when the click "succeeds" but produces no
                    # download — it already ends in
                    # _try_dropfiles_predicted_downloads, which is far more
                    # reliable against this WAF than repeating the browser
                    # click would be.
                    if site_type != "joomla_dropfiles":
                        raise
                if not downloads:
                    try:
                        await page.wait_for_event(
                            "download", timeout=min(DELAYED_DOWNLOAD_WAIT_MS, step_timeout_ms)
                        )
                    except Exception:
                        pass
                if downloads:
                    download = downloads.pop(0)
                    source_url = _download_source_url(download, page)
                    _skip = _normalized_href_patterns(recipe.get("href_skip_patterns"))
                    if _is_non_bulletin_url(source_url) or _href_is_skipped(
                        source_url, _skip
                    ):
                        downloads.clear()
                    else:
                        file_type = await _save_download_to_pdf(download, dest)
                        return dest, file_type, source_url
                picked = await _try_joomla_dropfiles_click_download(
                    page,
                    dest,
                    step_timeout_ms,
                    target_date=target_date,
                    example_href=dropfiles_example or (step.get("href") or "").strip(),
                )
                if picked:
                    return dest, picked[1], picked[0]
                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(
                        page, page.url, dest, timeout_ms=step_timeout_ms
                    )
                    return dest, file_type, source_url
                click_href = (step.get("href") or "").strip()
                if click_href:
                    resolved_href = urljoin(page.url, click_href)
                    href_candidates = _resolve_download_candidates(
                        resolved_href,
                        target_date=target_date,
                        use_captured_url=bool(step.get("use_captured_url")),
                    )
                    for candidate in href_candidates:
                        tried = await _try_download_page_url(
                            page, dest, candidate, timeout_ms=step_timeout_ms
                        )
                        if tried:
                            return dest, tried[1], tried[0]
                # Skip the blind "maybe page.url is secretly a document" probe
                # when more steps still follow this click. It duplicates the
                # _is_document_url(page.url) check just above (already False
                # here) with a real network round-trip, and _try_browser_nav_
                # download's fallback chain inside it can take ~200s on a
                # plain HTML listing page — for a click that only navigated
                # to an intermediate listing/category page (a later click or
                # a "download" step still to come), that time is wasted
                # since the next step handles the actual capture (found
                # 2026-08-09, parishoflisburn: click #1 navigated NEWS ->
                # /category/news/, this probe alone burned most of a 3-attempt
                # harvest budget before the real "Download" click on the next
                # step — which succeeds in under a second — ever ran).
                is_last_step = step_index == len(steps) - 1
                if is_last_step:
                    tried = await _try_download_page_url(page, dest, timeout_ms=step_timeout_ms)
                    if tried:
                        return dest, tried[1], tried[0]
                continue

            if action == "download":
                if downloads:
                    download = downloads.pop(0)
                    file_type = await _save_download_to_pdf(download, dest)
                    source_url = _download_source_url(download, page)
                    return dest, file_type, source_url

                pattern = (step.get("url_pattern") or "*.pdf").strip() or "*.pdf"
                step_url = (step.get("url") or "").strip()
                use_captured = bool(step.get("use_captured_url"))
                site_type = str(recipe.get("site_type") or "").lower()
                playbook = str(recipe.get("playbook_type") or "").lower()
                pdfemb_site = "pdfemb" in site_type or "wp_pdfemb" in site_type or playbook == "pdfemb"
                last_err = ""

                # PDF Embedder parishes: read live hrefs from the page — never rewrite a stale captured URL.
                if pdfemb_site and not _pattern_prefers_docx(pattern):
                    pdfemb_url = await _find_pdfemb_url(page, target_date=target_date)
                    if pdfemb_url:
                        try:
                            source_url, file_type = await _download_document_url(
                                page, pdfemb_url, dest, timeout_ms=step_timeout_ms
                            )
                            return dest, file_type, source_url
                        except RecipeReplayError as exc:
                            last_err = str(exc)

                if step.get("use_page_url"):
                    step_url = (page.url or "").strip()
                    if not _looks_like_http_url(step_url):
                        step_url = (last_http_url or start_url or "").strip()
                    use_captured = True
                download_candidates: list[str] = []
                if step_url and not pdfemb_site:
                    download_candidates = _resolve_download_candidates(
                        step_url,
                        target_date=target_date,
                        use_captured_url=use_captured,
                        use_target_url=bool(step.get("use_target_url")),
                    )
                for candidate in download_candidates:
                    tried = await _try_download_page_url(
                        page, dest, candidate, timeout_ms=step_timeout_ms
                    )
                    if tried:
                        return dest, tried[1], tried[0]

                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(
                        page, page.url, dest, timeout_ms=step_timeout_ms
                    )
                    return dest, file_type, source_url

                tried = await _try_download_page_url(page, dest, timeout_ms=step_timeout_ms)
                if tried:
                    return dest, tried[1], tried[0]

                pdfemb_url = await _find_pdfemb_url(page, target_date=target_date)
                if pdfemb_url and not _pattern_prefers_docx(pattern):
                    source_url, file_type = await _download_document_url(page, pdfemb_url, dest)
                    return dest, file_type, source_url

                # PDF iframe shortcut — skip when recipe asks for Word newsletters
                if not _pattern_prefers_docx(pattern):
                    iframe_pdf_url = await _find_iframe_pdf_url(page)
                    if iframe_pdf_url:
                        source_url, file_type = await _download_document_url(page, iframe_pdf_url, dest)
                        return dest, file_type, source_url

                mdocs_urls = await _find_mdocs_pdf_urls(page)
                for mdocs_url in mdocs_urls:
                    try:
                        source_url, file_type = await _download_document_url(
                            page, mdocs_url, dest, timeout_ms=step_timeout_ms
                        )
                        return dest, file_type, source_url
                    except RecipeReplayError as exc:
                        last_err = str(exc)
                        continue

                last_err = ""
                candidates = await _collect_document_candidates(page, pattern)
                per_candidate_ms = min(max(step_timeout_ms // max(len(candidates), 1), 8_000), 30_000)
                for resolved in candidates[:8]:
                    try:
                        source_url, file_type = await _download_document_url(
                            page, resolved, dest, timeout_ms=per_candidate_ms
                        )
                        return dest, file_type, source_url
                    except RecipeReplayError as exc:
                        last_err = str(exc)
                        continue

                if last_err:
                    raise RecipeReplayError(last_err)
                raise RecipeReplayError("Recipe download step did not find a matching document URL")

            if action == "image":
                raw_url = (step.get("url") or "").strip()
                if not raw_url:
                    raise RecipeReplayError("Recipe image step missing URL")
                source_url, file_type = await _download_image_url_as_pdf(page, raw_url, dest)
                return dest, file_type, source_url

            if action == "image_stack":
                try:
                    count = int(step.get("count") or 2)
                except (TypeError, ValueError) as exc:
                    raise RecipeReplayError("Recipe image_stack step has invalid count") from exc
                if count < 1:
                    raise RecipeReplayError("Recipe image_stack step count must be at least 1")

                try:
                    await page.wait_for_load_state("networkidle", timeout=min(step_timeout_ms, 30_000))
                except PlaywrightTimeoutError:
                    pass
                if step.get("scroll_bottom"):
                    try:
                        await page.evaluate(
                            "() => window.scrollTo(0, document.body.scrollHeight)"
                        )
                        await asyncio.sleep(1.5)
                    except Exception:
                        pass
                await asyncio.sleep(2.0)

                selector = (step.get("selector") or "").strip()
                position = str(step.get("position") or "first").strip().lower()
                if position not in {"first", "last"}:
                    raise RecipeReplayError(
                        'Recipe image_stack position must be "first" or "last"'
                    )
                try:
                    min_long_side = int(step.get("min_long_side") or 550)
                    min_short_side = int(step.get("min_short_side") or 500)
                except (TypeError, ValueError) as exc:
                    raise RecipeReplayError("Recipe image_stack step has invalid size filter") from exc

                image_urls = await _find_stacked_bulletin_image_urls(
                    page,
                    count,
                    selector=selector,
                    min_long_side=min_long_side,
                    min_short_side=min_short_side,
                    position=position,
                )
                if len(image_urls) < count:
                    raise RecipeReplayError(
                        f"Recipe image_stack found {len(image_urls)} bulletin image(s) but expected {count}"
                    )

                source_url, file_type = await _download_image_urls_as_pdf(
                    page, image_urls, dest, timeout_ms=step_timeout_ms
                )
                return dest, file_type, source_url

            if action == "html":
                html_url = (step.get("url") or "").strip() or page.url
                if not html_url:
                    raise RecipeReplayError("Recipe html step missing URL")
                if (step.get("url") or "").strip():
                    await page.goto(html_url, timeout=step_timeout_ms, wait_until="domcontentloaded")
                await _prepare_page_for_html_print(page, recipe, step_timeout_ms)
                print_wait_ms = 25_000 if _recipe_uses_parish_messenger(recipe) else 2500
                skip_nav = bool(step.get("skip_listing_nav", False))
                await _smart_print_page_to_pdf(
                    page, dest, target_date, wait_ms=print_wait_ms, skip_listing_nav=skip_nav,
                    max_pages=recipe.get("max_bulletin_pages"),
                )
                return dest, "print_to_pdf", html_url

            if action == "print_to_pdf":
                raw_pdf_url = (step.get("url") or "").strip()
                pdf_url = raw_pdf_url or page.url
                if not pdf_url:
                    raise RecipeReplayError("Recipe print_to_pdf step missing URL")
                _skip = _normalized_href_patterns(recipe.get("href_skip_patterns"))
                if _is_non_bulletin_url(pdf_url) or _href_is_skipped(pdf_url, _skip):
                    raise RecipeReplayError(
                        f"Refusing non-bulletin print_to_pdf URL: {pdf_url}"
                    )
                if raw_pdf_url:
                    await page.goto(pdf_url, timeout=step_timeout_ms, wait_until="domcontentloaded")
                await _prepare_page_for_html_print(page, recipe, step_timeout_ms)
                print_wait_ms = 25_000 if _recipe_uses_parish_messenger(recipe) else 2500
                skip_nav = bool(step.get("skip_listing_nav", False))
                await _smart_print_page_to_pdf(
                    page, dest, target_date, wait_ms=print_wait_ms, skip_listing_nav=skip_nav,
                    max_pages=recipe.get("max_bulletin_pages"),
                )
                return dest, "print_to_pdf", pdf_url

            if action == "crop_screenshot":
                sections = step.get("sections")
                if isinstance(sections, list) and sections:
                    # Multi-section crop: capture each section and stack vertically.
                    try:
                        from PIL import Image as PILImage
                    except ImportError as exc:
                        raise RecipeReplayError(
                            "Pillow is required for crop-screenshot bulletin conversion. Install with: pip install Pillow"
                        ) from exc

                    # Take one full-page screenshot shared across all sections.
                    screenshot_bytes = await page.screenshot(full_page=True)

                    try:
                        full_img = PILImage.open(io.BytesIO(screenshot_bytes))
                        cropped_parts: list = []
                        for sec in sections:
                            sx = int(sec.get("page_x", sec.get("x", 0)) or 0)
                            sy = int(sec.get("page_y", sec.get("y", 0)) or 0)
                            sw = int(sec.get("width", 0) or 0)
                            sh = int(sec.get("height", 0) or 0)
                            if sw <= 0 or sh <= 0:
                                continue
                            part = full_img.crop((sx, sy, sx + sw, sy + sh)).convert("RGB")
                            cropped_parts.append(part)

                        if not cropped_parts:
                            raise RecipeReplayError("No valid sections found in multi-section crop")

                        total_width = max(p.width for p in cropped_parts)
                        total_height = sum(p.height for p in cropped_parts)
                        combined = PILImage.new("RGB", (total_width, total_height), (255, 255, 255))
                        y_offset = 0
                        for part in cropped_parts:
                            combined.paste(part, (0, y_offset))
                            y_offset += part.height

                        combined.save(str(dest), "PDF", resolution=150)
                    except RecipeReplayError:
                        raise
                    except Exception as exc:
                        raise RecipeReplayError(f"Multi-section crop screenshot failed: {exc}") from exc

                    return dest, "crop_screenshot_to_pdf", page.url

                x = int(step.get("x", 0) or 0)
                y = int(step.get("y", 0) or 0)
                page_x = int(step.get("page_x", x) or x)
                page_y = int(step.get("page_y", y) or y)
                width = int(step.get("width", 0) or 0)
                height = int(step.get("height", 0) or 0)
                element_selector = str(step.get("element_selector", "") or "").strip()

                if width <= 0 or height <= 0:
                    raise RecipeReplayError("Recipe crop_screenshot step requires positive width/height")

                if element_selector:
                    try:
                        await page.locator(element_selector).first.scroll_into_view_if_needed(timeout=5000)
                    except Exception:
                        pass

                use_page_coords = "page_x" in step or "page_y" in step
                # page_x/page_y are absolute document coordinates, so capture the full page
                # before cropping. Otherwise viewport-only screenshots can crop the wrong area.
                screenshot_bytes = await page.screenshot(full_page=use_page_coords)

                try:
                    from PIL import Image as PILImage

                    img = PILImage.open(io.BytesIO(screenshot_bytes))
                    left = page_x if use_page_coords else x
                    top = page_y if use_page_coords else y
                    right = left + width
                    bottom = top + height
                    cropped = img.crop((left, top, right, bottom)).convert("RGB")
                    cropped.save(str(dest), "PDF", resolution=150)
                except ImportError as exc:
                    raise RecipeReplayError(
                        "Pillow is required for crop-screenshot bulletin conversion. Install with: pip install Pillow"
                    ) from exc
                except Exception as exc:
                    raise RecipeReplayError(f"Crop screenshot failed: {exc}") from exc

                return dest, "crop_screenshot_to_pdf", page.url

            raise RecipeReplayError(f"Unsupported recipe action: {action}")

        if downloads:
            download = downloads.pop(0)
            source_url = _download_source_url(download, page)
            _skip = _normalized_href_patterns(recipe.get("href_skip_patterns"))
            if _is_non_bulletin_url(source_url) or _href_is_skipped(source_url, _skip):
                downloads.clear()
            else:
                file_type = await _save_download_to_pdf(download, dest)
                return dest, file_type, source_url
        if _is_document_url(page.url):
            source_url, file_type = await _download_document_url(page, page.url, dest)
            return dest, file_type, source_url

        raise RecipeReplayError("Recipe finished without downloading a document")
    finally:
        try:
            await context.close()
        except Exception:
            pass
