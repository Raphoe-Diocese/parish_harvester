from __future__ import annotations

import asyncio
import fnmatch
import io
import json
import re
import subprocess
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

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
from .utils import (
    _is_within_opaque_hash,
    _opaque_hash_spans,
    extract_date_from_slug,
    extract_date_from_string,
    extract_newsletter_number,
    oneweb_newsletter_download_urls,
    predict_dropfiles_bulletin_urls,
    rewrite_date_url,
    rewrite_newsletter_number_for_target,
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

_NON_BULLETIN_RE = re.compile(
    r"dataentry|giftaid|standingorder|donation|prayer|safeguarding|privacy|gdpr|diocese|"
    r"sitemap|application|registration|volunteer|finances|financial|parishdraw|mcn\s*media|"
    r"gaza|bishops-call|bishops?[-_]?letter|pastoral[-_]?letter|draw_poster|poster_20\d{2}|"
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
_WP_UPLOADS_YEAR_MONTH_RE = re.compile(r"/wp-content/uploads/(20\d{2})/(0?[1-9]|1[0-2])/", re.IGNORECASE)


def _is_non_bulletin_url(url: str) -> bool:
    text = unquote(url or "")
    if _BULLETIN_KEYWORD_RE.search(text):
        return False
    return bool(_NON_BULLETIN_RE.search(text))


def _looks_like_http_url(url: str) -> bool:
    return (url or "").strip().lower().startswith(("http://", "https://"))


def _looks_like_direct_document_url(url: str) -> bool:
    lower = unquote((url or "").strip()).lower()
    if not _looks_like_http_url(lower):
        return False
    if "drive.usercontent.google.com/download" in lower:
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
        tried = await _try_download_page_url(page, dest, url, timeout_ms=timeout_ms)
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
        return ".pdf" in lower
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


async def _find_mdocs_pdf_urls(page: Page) -> list[str]:
    """mDocs plugin lists — latest bulletin is first row (site copy)."""
    raw_links = await page.eval_on_selector_all(
        "table.mdocs a[href], a.mdocs-download[href], .mdocs a[href], .mdocs-file a[href]",
        "(els) => els.map(el => el.getAttribute('href') || '').filter(Boolean)",
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in raw_links:
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = urljoin(page.url, raw.strip())
        lower = resolved.lower()
        if ".pdf" not in lower:
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
        probes.extend(["table.mdocs", "a.mdocs-download", ".mdocs a[href]"])
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


async def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        docx_path = tmp_path / "bulletin.docx"
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
    Playwright navigation to the identical URL. urlopen already follows the
    redirect chain (SEF URL -> index.php?task=frontfile.download -> file)
    transparently, so only the final response matters here.
    """
    started = time.monotonic()
    attempts = 0
    while attempts < max_attempts and (time.monotonic() - started) < total_budget_s:
        attempts += 1
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=per_attempt_timeout_s) as response:
                body = response.read()
                if response.status == 200 and body:
                    headers = {k.lower(): v for k, v in response.headers.items()}
                    return body, headers
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
    if _is_pdf_content(body) or body[:2] == b"PK":  # PK = docx/zip signature
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
                    file_result = await asyncio.to_thread(
                        _fetch_bytes_with_retries,
                        best_url,
                        max_attempts=_DROPFILES_HTTP_ATTEMPTS,
                        per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
                        total_budget_s=min(_DROPFILES_HTTP_FILE_BUDGET_S, _remaining_budget()),
                    )
                    if file_result:
                        file_body, file_headers = file_result
                        if _dropfiles_body_looks_like_file(file_headers, file_body):
                            try:
                                file_type = await _save_dropfiles_bytes_to_pdf(
                                    file_body, file_headers, best_url, dest
                                )
                                return best_url, file_type
                            except RecipeReplayError:
                                pass

    if example_href:
        for candidate in predict_dropfiles_bulletin_urls(example_href, target_date)[:4]:
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


def _extract_matching_hrefs(html: str, base_url: str, keyword_patterns: list[str]) -> list[str]:
    """Plain-regex href extraction (no bs4 dependency) for WAF-flaky sites where
    we fetch raw HTML via plain HTTP retries instead of a Playwright DOM."""
    out: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', html):
        low = href.lower()
        if not any(pat in low for pat in keyword_patterns):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def _extract_pdfembed_target_url(html: str) -> str | None:
    """PDF Embedder plugin iframe: src="...?url=<urlencoded pdf url>&title=...".
    Same plugin/markup as PDFEMB_SELECTOR (a.pdfemb-viewer) used elsewhere,
    just accessed via raw HTML regex instead of a Playwright locator."""
    m = _PDFEMB_IFRAME_SRC_RE.search(html)
    if not m:
        return None
    src = m.group(1) or m.group(2)
    if not src:
        return None
    query = parse_qs(urlparse(unquote(src)).query)
    urls = query.get("url")
    return urls[0] if urls else None


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
    3. Fetch that post page and pull out either a PDF Embedder iframe's
       target PDF, or the post's own (non-thumbnail) uploaded page image(s).
    4. Fetch the actual file(s) and save/convert to *dest* as a PDF.

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

    if _remaining_budget() <= 0:
        return None
    listing_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        listing_url,
        max_attempts=_DROPFILES_HTTP_ATTEMPTS,
        per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
        total_budget_s=_stage_budget(_DROPFILES_HTTP_LISTING_BUDGET_S),
    )
    if not listing_result:
        return None
    listing_body, listing_headers = listing_result
    if "text/html" not in (listing_headers.get("content-type") or "").lower():
        return None
    listing_html = listing_body.decode("utf-8", errors="ignore")

    candidates = _extract_matching_hrefs(listing_html, listing_url, post_slug_patterns)
    scored: list[tuple[date, str]] = []
    for href in candidates:
        slug = urlparse(href).path.rstrip("/").rsplit("/", 1)[-1]
        found = extract_date_from_slug(slug) or extract_date_from_string(slug)
        if found and found <= target_date + timedelta(days=3):
            scored.append((found, href))
    if not scored:
        return None
    _best_date, post_url = max(scored)

    if _remaining_budget() <= 0:
        return None
    post_result = await asyncio.to_thread(
        _fetch_bytes_with_retries,
        post_url,
        max_attempts=_DROPFILES_HTTP_ATTEMPTS,
        per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
        total_budget_s=_stage_budget(_DROPFILES_HTTP_FILE_BUDGET_S),
    )
    if not post_result:
        return None
    post_body, post_headers = post_result
    if "text/html" not in (post_headers.get("content-type") or "").lower():
        return None
    post_html = post_body.decode("utf-8", errors="ignore")

    pdf_url = _extract_pdfembed_target_url(post_html)
    if pdf_url and _remaining_budget() > 0:
        pdf_url = urljoin(post_url, pdf_url)
        file_result = await asyncio.to_thread(
            _fetch_bytes_with_retries,
            pdf_url,
            max_attempts=_DROPFILES_HTTP_ATTEMPTS,
            per_attempt_timeout_s=_DROPFILES_HTTP_PER_ATTEMPT_TIMEOUT_S,
            total_budget_s=_stage_budget(_DROPFILES_HTTP_FILE_BUDGET_S),
        )
        if file_result:
            file_body, file_headers = file_result
            if _dropfiles_body_looks_like_file(file_headers, file_body) and _is_pdf_content(
                file_body
            ):
                dest.write_bytes(file_body)
                return pdf_url, "pdf"

    image_urls = _extract_wp_upload_images(
        post_html, _best_date.year, _best_date.month, post_url
    )
    if image_urls:
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
) -> list[str]:
    step_url = (step_url or "").strip()
    if not step_url:
        return []
    if use_captured_url or not target_date:
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
            if any(tag in playbook.lower() for tag in ("pdfemb", "mdocs", "wp_block", "permanent_bulletin", "mcn_live", "mcn_pdf")):
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
) -> int | None:
    """Pattern H: pick highest /Newsletters/NNN/, /Weekly-Bulletins/NNN/, or /Bulletins/NNN/ number."""
    ranks: list[tuple[int, int, int]] = []
    for ent in entries:
        resolved = urljoin(page_url, ent["href"])
        if resolved and _is_non_bulletin_url(resolved):
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
) -> int | None:
    best_idx: int | None = None
    best_rank: tuple[int, int] = (-1, -1)
    for ent in entries:
        resolved = urljoin(page_url, ent["href"])
        if resolved and _is_non_bulletin_url(resolved):
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
            count = len(entries)

            if strategy == "first_match":
                await _click_locator_match(page, locator.nth(entries[0]["idx"]), step_timeout_ms)
                return True
            if strategy == "last_match":
                await _click_locator_match(
                    page, locator.nth(entries[-1]["idx"]), step_timeout_ms
                )
                return True

            newsletter_idx = _best_newsletter_link_index(
                entries, page.url, position=position
            )
            if newsletter_idx is not None:
                await _click_locator_match(page, locator.nth(newsletter_idx), step_timeout_ms)
                return True

            best_idx = _best_scored_link_index(entries, page.url, position=position)
            if best_idx is not None:
                await _click_locator_match(page, locator.nth(best_idx), step_timeout_ms)
                return True

            # _best_scored_link_index already excludes non-bulletin URLs
            # (GDPR/Safeguarding/Privacy notice etc.) and returned None
            # here because every matched entry was one of those. Never fall
            # back to blindly clicking entries[0]/entries[-1] in that case —
            # that silently harvests a GDPR/Safeguarding PDF as "the
            # bulletin" (seen on camusparish, leckpatrickparish). Only fall
            # back among the remaining genuine candidates, if any.
            safe_entries = [
                ent for ent in entries
                if not _is_non_bulletin_url(urljoin(page.url, ent["href"]))
            ]
            if not safe_entries:
                errors.append(
                    f"{sel}: only non-bulletin links matched (GDPR/Safeguarding/"
                    "Privacy notice etc.) — no genuine bulletin link found"
                )
                continue

            fallback_idx = safe_entries[-1]["idx"] if position == "bottom" else safe_entries[0]["idx"]
            await _click_locator_match(page, locator.nth(fallback_idx), step_timeout_ms)
            return True
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    if errors:
        raise RecipeReplayError("; ".join(errors[:MAX_SELECTOR_ERRORS]))
    return False


async def _open_selected_drive_row(page: Page, timeout_ms: int) -> None:
    """Open the Drive folder row just clicked.

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
    try:
        file_id = await page.evaluate(
            "() => { const row = document.querySelector('[role=\"row\"][aria-selected=\"true\"]'); "
            "return row ? row.getAttribute('data-id') : null; }"
        )
    except Exception:
        file_id = None
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


async def _replay_click(
    page: Page,
    step: dict,
    step_timeout_ms: int,
    *,
    target_date: date | None = None,
) -> None:
    is_cloud_folder = is_cloud_folder_click_step(step)
    if target_date:
        if is_year_folder_click_step(step):
            step = rewrite_year_folder_click_step(step, target_date)
        if is_cloud_folder_click_step(step):
            step = rewrite_cloud_folder_click_step(step, target_date)
            is_cloud_folder = True

    selectors: list[str] = []
    selector = (step.get("selector") or "").strip()
    if selector:
        selectors.append(selector)
    selectors.extend(
        s.strip() for s in step.get("fallback_selectors", []) if isinstance(s, str) and s.strip()
    )

    if not selectors:
        raise RecipeReplayError("Recipe click step missing selector")

    if step.get("pick_strategy"):
        if await _replay_click_by_strategy(page, step, selectors, step_timeout_ms):
            if is_cloud_folder:
                await _open_selected_drive_row(page, step_timeout_ms)
            return

    errors: list[str] = []
    for sel in selectors:
        try:
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
        found = await _try_waf_retry_wordpress_bulletin(
            start_url,
            dest,
            post_slug_patterns=post_slug_patterns,
            target_date=target_date,
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
                await _replay_click(page, step, step_timeout_ms, target_date=target_date)
                if not downloads:
                    try:
                        await page.wait_for_event(
                            "download", timeout=min(DELAYED_DOWNLOAD_WAIT_MS, step_timeout_ms)
                        )
                    except Exception:
                        pass
                if downloads:
                    download = downloads.pop(0)
                    file_type = await _save_download_to_pdf(download, dest)
                    source_url = _download_source_url(download, page)
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
            file_type = await _save_download_to_pdf(download, dest)
            return dest, file_type, _download_source_url(download, page)
        if _is_document_url(page.url):
            source_url, file_type = await _download_document_url(page, page.url, dest)
            return dest, file_type, source_url

        raise RecipeReplayError("Recipe finished without downloading a document")
    finally:
        try:
            await context.close()
        except Exception:
            pass
