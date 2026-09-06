"""
utils.py — Shared helper utilities for the Parish Bulletin Harvester.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse


def format_uk_date(iso_date: str | date | None) -> str:
    """Format a date for display as DD/MM/YYYY (UK). Pass-through if unparseable."""
    if iso_date is None:
        return ""
    if isinstance(iso_date, date) and not isinstance(iso_date, datetime):
        return iso_date.strftime("%d/%m/%Y")
    raw = str(iso_date or "").strip()
    if not raw:
        return ""
    # Accept YYYY-MM-DD or full ISO timestamps.
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# Date-pattern helpers
# ---------------------------------------------------------------------------

_DDMMYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")      # 310825
_DDMMYYYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")    # 31082025
_YY_MM_DD_RE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{2})(?!\d)")  # 26.06.14
# DD.MM.YYYY — Kilmore Newsletter-23.08.2026.pdf. Must be tried before the
# 2-digit-year dotted forms so "23.08.2026" is not read as 08.20.26.
_D_M_YYYY_DOT_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")                     # 2025-08-31
_ISO_NODASH_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")  # 20250831
_WP_YEAR_MONTH_RE = re.compile(r"/(\d{4})/(\d{2})/")                 # /2026/04/

# Pattern G: WordPress date-based post slug /YYYY/MM/DD/slug/
# e.g. clonleighparish.com/2026/04/03/strabane-pastoral-area-newsletter.../
_WP_DATE_POST_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[^/]+/")

# Lighter variant: matches just the /YYYY/MM/DD/ path segment (no slug required).
# Used by _find_dated_bulletin_link() to extract publish dates from WP post URLs.
_WP_DATE_PATH_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

# Pattern B: D-M-YY (1–2 digit day/month, 2-digit year, dash-separated)
# e.g. 5-4-26, 12-4-26, 15-3-26  (Limavady parish pattern)
_D_M_YY_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)")

# Pattern B-dot: D.M.YY with optional unpadded month/day — Ballymena
# 16.8.26-20th-Sunday.pdf / 9.8.26-19th-Sunday.pdf. The 2-digit-only
# _YY_MM_DD_RE above does not match these.
_D_M_YY_DOT_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)")

# Pattern E: [YYYY-M-D] bracketed ISO variant
# e.g. [2026-4-12], [2026-12-25]  (Greenlough parish pattern)
_BRACKETED_ISO_RE = re.compile(r"\[(\d{4})-(\d{1,2})-(\d{1,2})\]")

# Month name → month number mapping (English, full and abbreviated)
_MONTH_MAP: dict[str, int] = {
    "january": 1,  "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,    "mar": 3,
    "april": 4,    "apr": 4,
    "may": 5,
    "june": 6,     "jun": 6,
    "july": 7,     "jul": 7,
    "august": 8,   "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Matches date slugs like "5_april_2026", "15-february-2026", "5th-April-2026",
# and space-separated filenames decoded from URLs like "Parish Bulletin 9th
# August 2026.pdf" (GoDaddy/wsimg CDN downloads — %20 unquotes to a literal
# space, not a dash/underscore). The optional ordinal suffix
# (?:st|nd|rd|th)? handles formats like "5th" or "12th".
# Yearless "9th-August" / "5th July" slugs (Milford & Rathmullan overwrite
# Parish-Newsletter-Sunday-9th-August.pdf each week with no year in the
# filename). Negative lookahead refuses a following 2–4 digit year so
# "9th-August-2026" stays with the dated slug matcher and Kincasslagh
# archive "org_6-sep-15.pdf" is not read as 06/09/2026.
_MONTH_ALT = "|".join(sorted(_MONTH_MAP.keys(), key=len, reverse=True))
# Separators are one-or-more so Inver's "30th__august_2026" still matches.
# Year may be 2026 or '26 (Ardara "sun-30th-august-26"). Month names only —
# [a-z]+ used to eat "sun" + the "30" of "30th" and hide the real date.
# (?<!\d) stops "2026-August-16" being read as 26 August 2016.
_SLUG_DATE_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[_\-\s+]+({_MONTH_ALT})[_\-\s+]+(20\d{{2}}|\d{{2}})",
    re.IGNORECASE,
)
_YEARLESS_SLUG_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[_\-\s+]({_MONTH_ALT})"
    rf"(?![a-z])(?![_\-\s+]\d{{2,4}})",
    re.IGNORECASE,
)

# Glenavy: 2026-August-16-Twentieth-Sunday-in-Ordinary-Time.pdf
_YEAR_MONTHNAME_DAY_RE = re.compile(
    rf"(20\d{{2}})[_\-\s]({_MONTH_ALT})[_\-\s](\d{{1,2}})(?:st|nd|rd|th)?(?!\d)",
    re.IGNORECASE,
)

# Tawnawilly listing 2026-09-06: Sunday-Sept-06-26.pdf (Month-DD-YY),
# not Sunday-6th-Sept.pdf (that name 404s).
_MONTH_DAY_YY_RE = re.compile(
    rf"(?<![A-Za-z])({_MONTH_ALT})[_\-\s+](\d{{1,2}})(?:st|nd|rd|th)?[_\-\s+](20\d{{2}}|\d{{2}})(?!\d)",
    re.IGNORECASE,
)

_MONTH_NAMES: list[str] = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


# Opaque hash/ID guard — Wix, Squarespace and similar CDNs serve files under
# random hex hashes (e.g. /_files/ugd/18d125_593092963abf434abc12c3fd7104b6d4.pdf).
# A bare 6- or 8-digit run inside a long hex token can coincidentally look like
# a DDMMYY/DDMMYYYY/YYYYMMDD date (e.g. "...e290776b..." parsed as 29/07/76),
# producing a bogus "bulletin date" that then gets rejected as stale/future.
# Any digit-run match fully contained inside such a token is not a real date.
_HEX_TOKEN_RE = re.compile(r"[0-9a-fA-F]+")
_OPAQUE_HASH_MIN_LEN = 16
# GoDaddy/wsimg-style CDN paths embed standard RFC4122 UUIDs
# (8-4-4-4-12 hex groups, hyphen-separated), e.g.
# ".../108951e4-fc38-47c8-9aaf-adae09d28d1b/Parish-Bulletin-...". Each
# dash-separated group is individually shorter than _OPAQUE_HASH_MIN_LEN, so
# the bare hex-run check above misses them — "108951" inside "108951e4" was
# read as day=10/month=89/year=2051 (found 2026-08-09,
# saintmichaelthearchangel). Match the whole hyphenated UUID as one span.
_UUID_TOKEN_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# WordPress media-library auto-generated filenames like
# "Document_240328_120527.pdf" (upload YYMMDD_HHMMSS timestamp, not a
# bulletin date). The trailing 6 digits are themselves a valid-looking
# HHMMSS, and the leading 6 digits can independently misparse as a *valid*
# DDMMYY date (e.g. "240328" -> day=24/month=03/year=2028) — since it's a
# real constructible date(), the existing date()-validation guard doesn't
# catch it, and being a future year it silently outranks every genuinely
# dated bulletin link on the page (found 2026-08-10, bangorparish:
# pick_strategy:newest_dated grabbed an unrelated 2024-uploaded PDF instead
# of the real June 2026 newsletter because of this). Treat the whole
# 6-digit_6-digit pair as opaque, like a hash/UUID.
_TIMESTAMP_PAIR_RE = re.compile(r"(?<!\d)\d{6}[_-]\d{6}(?!\d)")


def _opaque_hash_spans(text: str) -> list[tuple[int, int]]:
    """Spans of long hex-looking tokens (likely CDN hashes/UUIDs, not dates)."""
    spans = []
    for m in _UUID_TOKEN_RE.finditer(text):
        spans.append((m.start(), m.end()))
    for m in _TIMESTAMP_PAIR_RE.finditer(text):
        spans.append((m.start(), m.end()))
    for m in _HEX_TOKEN_RE.finditer(text):
        token = m.group(0)
        if len(token) >= _OPAQUE_HASH_MIN_LEN and re.search(r"[a-fA-F]", token):
            spans.append((m.start(), m.end()))
    return spans


def _is_within_opaque_hash(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def _first_match_outside_hash(
    pattern: re.Pattern, text: str, spans: list[tuple[int, int]]
) -> re.Match | None:
    """Like pattern.search(text), but skips matches inside opaque hash tokens."""
    for m in pattern.finditer(text):
        if not _is_within_opaque_hash(spans, m.start(), m.end()):
            return m
    return None


def _ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _slug_had_ordinal(slug_fragment: str) -> bool:
    return bool(re.search(r"\d{1,2}(?:st|nd|rd|th)\b", slug_fragment, re.IGNORECASE))


def _year_from_slug_digits(raw: str) -> int | None:
    """Turn a slug year group into a 4-digit year (26 → 2026)."""
    text = (raw or "").strip()
    if not text.isdigit():
        return None
    if len(text) == 2:
        return 2000 + int(text)
    return int(text)


def _date_from_month_first_match(match: re.Match[str]) -> date | None:
    month = _MONTH_MAP.get(match.group(1).lower())
    if not month:
        return None
    year = _year_from_slug_digits(match.group(3))
    if year is None or not _is_plausible_bulletin_year(year):
        return None
    try:
        return date(year, month, int(match.group(2)))
    except ValueError:
        return None


def _date_from_slug_match(match: re.Match[str]) -> date | None:
    month = _MONTH_MAP.get(match.group(2).lower())
    if not month:
        return None
    year = _year_from_slug_digits(match.group(3))
    if year is None or not _is_plausible_bulletin_year(year):
        return None
    try:
        return date(year, month, int(match.group(1)))
    except ValueError:
        return None


def _first_slug_date_match(text: str) -> tuple[re.Match[str], date] | None:
    """First slug date whose month name is real (skip 'sun' in weekend ranges)."""
    for match in _SLUG_DATE_RE.finditer(text or ""):
        parsed = _date_from_slug_match(match)
        if parsed:
            return match, parsed
    return None


def _is_plausible_bulletin_year(year: int) -> bool:
    """Reject years so far in the past/future they can only be a parsing
    artifact, not a real bulletin date.

    A raw 4-digit-year match (ISO/DDMMYYYY) is otherwise only checked by
    Python's date() constructor, which happily accepts any year 1-9999 — a
    typo'd archive filename like "22107018.pdf" parses under DDMMYYYY as
    day=22/month=10/year=7018, a "valid" date() that then silently outranks
    every genuinely dated 2020s bulletin link on the page (found
    2026-08-10, kincasslagh: picked an 18th July 2021 PDF instead of the
    real 5th July 2026 newsletter because of this). Parish bulletin
    archives realistically span at most a few decades back and are never
    dated more than ~2 years ahead of today.
    """
    today = date.today()
    return (today.year - 50) <= year <= (today.year + 2)


def extract_date_from_string(text: str) -> date | None:
    """Try to parse a date from a filename/URL fragment. Returns None on failure."""
    spans = _opaque_hash_spans(text)

    # ISO with dashes
    m = _first_match_outside_hash(_ISO_RE, text, spans)
    if m:
        try:
            candidate = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if _is_plausible_bulletin_year(candidate.year):
                return candidate
        except ValueError:
            pass

    # ISO without dashes (8 digits)
    m = _first_match_outside_hash(_ISO_NODASH_RE, text, spans)
    if m:
        try:
            candidate = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if _is_plausible_bulletin_year(candidate.year):
                return candidate
        except ValueError:
            pass

    # DDMMYYYY (8 digits)
    m = _first_match_outside_hash(_DDMMYYYY_RE, text, spans)
    if m:
        try:
            candidate = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if _is_plausible_bulletin_year(candidate.year):
                return candidate
        except ValueError:
            pass

    # DDMMYY (6 digits) — interpret YY as 2000+YY
    m = _first_match_outside_hash(_DDMMYY_RE, text, spans)
    if m:
        try:
            year = 2000 + int(m.group(3))
            return date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # DD.MM.YYYY (4-digit year is unambiguous UK dots).
    m = _first_match_outside_hash(_D_M_YYYY_DOT_RE, text, spans)
    if m:
        try:
            candidate = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if _is_plausible_bulletin_year(candidate.year):
                return candidate
        except ValueError:
            pass

    # Pattern B: D-M-YY (1–2 digit day/month). Ambiguous between UK
    # DD-MM-YY (limavady 16-8-26.pdf, claudy NEWSLETTER 9-8-26.docx) and
    # YY-MM-DD (ballymoneyparish 26-08-23pdf.pdf → 23/08/2026). Reading
    # Ballymoney as DD-MM-YY made this week's file look like 2016/2023 and
    # harvest rejected it (found 2026-08-23). Same later-year pick as the
    # dotted form below. Must come after the 6/8-digit compact forms so
    # "160826" is not split into 16-08-26 by accident (those have no dashes).
    m = _first_match_outside_hash(_D_M_YY_RE, text, spans)
    if m:
        g1, g2, g3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dashed: list[date] = []
        try:
            dashed.append(date(2000 + g1, g2, g3))  # YY-MM-DD
        except ValueError:
            pass
        try:
            dashed.append(date(2000 + g3, g2, g1))  # DD-MM-YY
        except ValueError:
            pass
        plausible_dashed = [c for c in dashed if _is_plausible_bulletin_year(c.year)]
        if plausible_dashed:
            return max(plausible_dashed, key=lambda d: (d.year, d.month, d.day))

    # Dot-separated N.N.NN — ambiguous between YY.MM.DD (Google Drive folder
    # rows: 26.06.14 → 2026-06-14, 29.01.05 → 2029-01-05; locked by
    # tests/test_cloud_folders.py) and UK-convention DD.MM.YY filenames
    # (stbrigidsparishbelfast.org's "Parish-Bulletin-09.08.26-FOR-PRINTING.pdf",
    # where reading it as YY.MM.DD gives a bogus 2009-08-26 and makes a genuinely
    # current bulletin look 17 years stale). The middle group is the month
    # under both readings, so only the outer two groups swap between "day" and
    # "year". Try both, keep only the readings that are calendar-valid, and
    # prefer whichever implies the later (more plausible/current) year — this
    # matches both locked Drive-folder cases above and the UK bulletin case.
    m = _first_match_outside_hash(_YY_MM_DD_RE, text, spans)
    if m:
        g1, g2, g3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        candidates: list[date] = []
        try:
            candidates.append(date(2000 + g1, g2, g3))  # YY.MM.DD
        except ValueError:
            pass
        try:
            candidates.append(date(2000 + g3, g2, g1))  # DD.MM.YY
        except ValueError:
            pass
        if candidates:
            # Prefer the reading nearer today. max(year) turned St Brigid's
            # Parish-Bulletin-30.08.26 into 2030-08-26 (found 2026-09-06).
            # Drive folder 26.06.14 → 2026-06-14 and 29.01.05 → 2029-01-05
            # stay the nearer reading.
            today = date.today()
            return min(candidates, key=lambda d: abs((d - today).days))

    # Pattern B-dot with unpadded day/month (16.8.26 / 9.8.26). Same dual
    # year reading as the 2-digit dotted form above. Must run after that
    # form so 26.06.14 still hits the locked Drive-folder tests first.
    m = _first_match_outside_hash(_D_M_YY_DOT_RE, text, spans)
    if m:
        g1, g2, g3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        candidates = []
        try:
            candidates.append(date(2000 + g1, g2, g3))  # YY.MM.DD
        except ValueError:
            pass
        try:
            candidates.append(date(2000 + g3, g2, g1))  # DD.MM.YY
        except ValueError:
            pass
        plausible = [c for c in candidates if _is_plausible_bulletin_year(c.year)]
        if plausible:
            today = date.today()
            return min(plausible, key=lambda d: abs((d - today).days))

    # Ordinal month-name slugs: 26th-July-2026, 5_april_2026
    slug_date = extract_date_from_slug(text)
    if slug_date:
        return slug_date

    # Year-first month-name: 2026-August-16 (Glenavy / Killead)
    m = _first_match_outside_hash(_YEAR_MONTHNAME_DAY_RE, text, spans)
    if m:
        month = _MONTH_MAP.get(m.group(2).lower())
        if month:
            try:
                candidate = date(int(m.group(1)), month, int(m.group(3)))
                if _is_plausible_bulletin_year(candidate.year):
                    return candidate
            except ValueError:
                pass

    # Month-first: Sunday-Sept-06-26.pdf (Tawnawilly, found 2026-09-06)
    m = _first_match_outside_hash(_MONTH_DAY_YY_RE, text, spans)
    if m:
        parsed = _date_from_month_first_match(m)
        if parsed:
            return parsed

    return None


# Tawnawilly yearless Aug rewrites to Sep; listing says Sept (found 2026-09-06).
# Roslea dated August rewrites to September; live file is Sept-2026.
_MONTH_NAME_VARIANTS: dict[int, tuple[str, ...]] = {
    1: ("Jan", "January"),
    2: ("Feb", "February"),
    3: ("Mar", "March"),
    4: ("Apr", "April"),
    5: ("May",),
    6: ("Jun", "June"),
    7: ("Jul", "July"),
    8: ("Aug", "August"),
    9: ("Sep", "Sept", "September"),
    10: ("Oct", "October"),
    11: ("Nov", "November"),
    12: ("Dec", "December"),
}


def month_name_filename_variants(url: str) -> list[str]:
    """Extra Sep/Sept/September (etc.) filenames after a month-name rewrite.

    Covers yearless slugs (Sunday-6th-Sep.pdf) and dated slugs
    (Bulletin-Sunday-6th-September-2026.pdf).
    """
    parsed = urlparse(url)
    path = unquote(parsed.path or "")
    match = _SLUG_DATE_RE.search(path) or _YEARLESS_SLUG_RE.search(path)
    if not match:
        return []
    raw = match.group(2)
    month = _MONTH_MAP.get(raw.lower())
    if not month:
        return []
    out: list[str] = []
    for name in _MONTH_NAME_VARIANTS.get(month, ()):
        if name.lower() == raw.lower():
            continue
        if raw.isupper():
            repl = name.upper()
        elif raw[0].isupper():
            repl = name[0].upper() + name[1:]
        else:
            repl = name.lower()
        new_path = path[: match.start(2)] + repl + path[match.end(2) :]
        out.append(parsed._replace(path=new_path).geturl())
    return out


def yearless_month_name_variants(url: str) -> list[str]:
    """Alias kept for tests; same as month_name_filename_variants."""
    return month_name_filename_variants(url)


def month_first_sunday_upload_urls(example_url: str, week: date) -> list[str]:
    """Guess Sunday-Sept-06-26.pdf from a yearless Sunday-23rd-Aug.pdf example.

    Tawnawilly's 06/09/2026 listing uses Month-DD-YY. Sunday-6th-Sept.pdf 404s.
    Only for yearless / month-first Sunday files with no /YYYY/MM/ folder.
    """
    raw = (example_url or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw)
    path = unquote(parsed.path or "")
    leaf = path.rsplit("/", 1)[-1]
    if "sunday" not in leaf.lower():
        return []
    if re.search(r"/\d{4}/\d{2}/", path):
        return []
    if not (_YEARLESS_SLUG_RE.search(leaf) or _MONTH_DAY_YY_RE.search(leaf)):
        return []
    directory = path.rsplit("/", 1)[0]
    yy = f"{week.year % 100:02d}"
    day_pad = f"{week.day:02d}"
    day_raw = str(week.day)
    names: list[str] = []
    # Listing uses Sept, not Sep / September.
    month_names = _MONTH_NAME_VARIANTS.get(week.month, ())
    if week.month == 9:
        month_names = ("Sept", "Sep", "September")
    for name in month_names:
        cap = name[0].upper() + name[1:]
        for day in (day_pad, day_raw):
            names.append(f"Sunday-{cap}-{day}-{yy}.pdf")
            names.append(f"Sunday-{cap}-{day}-{week.year}.pdf")
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        url = parsed._replace(path=f"{directory}/{name}").geturl()
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def yearless_slug_date(
    text: str,
    assume_year: int,
    *,
    near: date | None = None,
) -> date | None:
    """Parse a yearless '9th-August' / '5th July' slug using *assume_year*.

    If the resulting date is more than 14 days ahead of *near* (typically
    the harvest Sunday), try the previous year — so a 04/01 harvest still
    reads '28th-December' as last December, not next December.
    """
    m = _YEARLESS_SLUG_RE.search(unquote(text or ""))
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(2).lower())
    if not month:
        return None
    try:
        candidate = date(assume_year, month, int(m.group(1)))
    except ValueError:
        return None
    if near is not None and (candidate - near).days > 14:
        try:
            return date(assume_year - 1, month, int(m.group(1)))
        except ValueError:
            return candidate
    return candidate


def quote_http_url(url: str) -> str:
    """Encode raw spaces in a URL path so urllib can fetch it.

    Listing pages (Clones) often publish ``href="/uploads/downloads/Sunday
    23rd August 2026.pdf"`` with a literal space. ``urljoin`` keeps that
    space; ``urllib.request.Request`` then raises ``InvalidURL``. Already
    encoded ``%20`` stays ``%20`` (unquote, then quote).
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    return parsed._replace(path=quote(unquote(parsed.path), safe="/")).geturl()


# Antrim www-static filenames: 23rd-August-2026.pdf and the live doubled-month
# quirk 30th-August-August-2026-1-1.pdf (plain 30th-August-2026.pdf is 404).
_ANTRIM_ORDINAL_PDF_RE = re.compile(
    rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)-"
    rf"(?P<month>{_MONTH_ALT})"
    rf"(?:-(?P<month2>{_MONTH_ALT}))?"
    rf"-(?P<year>20\d{{2}})"
    rf"(?:-1(?:-1)?)?"
    rf"\.pdf$",
    re.IGNORECASE,
)


def antrim_doubled_month_pdf_urls(example_url: str, week: date) -> list[str]:
    """Antrim-only ordinal PDF names, including doubled-month -1-1 variants.

    Scoped to antrimparish.com. Does not invent names for other hosts or for
    non-bulletin files such as Volunteer-EOI-form.pdf.
    """
    raw = (example_url or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw)
    if "antrimparish.com" not in (parsed.netloc or "").lower():
        return []
    leaf = unquote(parsed.path).rstrip("/").rsplit("/", 1)[-1]
    if not _ANTRIM_ORDINAL_PDF_RE.search(leaf):
        return []
    rewritten = rewrite_date_url(raw, week)
    parsed_r = urlparse(rewritten)
    directory = unquote(parsed_r.path).rsplit("/", 1)[0]
    directory = re.sub(
        r"/\d{4}/\d{2}$",
        f"/{week.year}/{week.month:02d}",
        directory,
    )
    day_ord = f"{week.day}{_ordinal_suffix(week.day)}"
    month = _MONTH_NAMES[week.month].capitalize()
    year = week.year
    names = (
        f"{day_ord}-{month}-{year}.pdf",
        f"{day_ord}-{month}-{year}-1.pdf",
        f"{day_ord}-{month}-{year}-1-1.pdf",
        f"{day_ord}-{month}-{month}-{year}.pdf",
        f"{day_ord}-{month}-{month}-{year}-1.pdf",
        f"{day_ord}-{month}-{month}-{year}-1-1.pdf",
    )
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        url = parsed_r._replace(path=f"{directory}/{name}").geturl()
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def predicted_dated_upload_urls(
    example_url: str,
    target: date,
    *,
    weeks_back: int = 8,
    weeks_ahead: int = 0,
) -> list[str]:
    """Rewrite a dated upload URL for *target* and nearby Sundays.

    Tries *weeks_ahead* future Sundays first (default 0 so urls[0] stays
    the current Sunday), then *target*, then the previous *weeks_back*
    Sundays. Also tries .docx/.jpg/.jpeg/.png siblings of each .pdf guess
    (uploader fallback).
    """
    seen: list[str] = []
    weeks_back = max(0, int(weeks_back or 0))
    weeks_ahead = max(0, int(weeks_ahead or 0))

    def _add(url: str) -> None:
        url = (url or "").strip()
        if url and url not in seen:
            seen.append(url)

    for i in range(-weeks_ahead, weeks_back + 1):
        week = target - timedelta(days=7 * i)
        ordinary = rewrite_ordinary_time_upload_url(example_url, week)
        if ordinary:
            _add(ordinary)
        rewritten = rewrite_date_url(example_url, week)
        forms = [rewritten, *month_name_filename_variants(rewritten)]
        forms.extend(month_first_sunday_upload_urls(example_url, week))
        for form in forms:
            _add(form)
            lower = form.lower()
            if lower.endswith(".pdf"):
                stem = form[:-4]
                for ext in (".docx", ".jpg", ".jpeg", ".png"):
                    _add(stem + ext)
            elif lower.endswith(".docx"):
                _add(form[:-5] + ".pdf")
                parsed = urlparse(form)
                quoted = parsed._replace(path=quote(unquote(parsed.path), safe="/")).geturl()
                _add(quoted)
        if "onewebmedia" in rewritten.lower() and "newsletter" in rewritten.lower():
            for extra in oneweb_newsletter_download_urls(example_url, week):
                _add(extra)
        for extra in antrim_doubled_month_pdf_urls(example_url, week):
            _add(extra)
    return seen


def extract_date_from_slug(slug: str) -> date | None:
    """
    Extract a date from a URL slug like '5_april_2026' or '15-february-2026'.

    Weekend ranges such as ``sat_29th__-_sun_30th__august_2026`` keep the
    later real month-name date (the Sunday). Returns None if no
    recognisable date pattern is found.
    """
    found: list[date] = []
    for match in _SLUG_DATE_RE.finditer(slug or ""):
        parsed = _date_from_slug_match(match)
        if parsed:
            found.append(parsed)
    return max(found) if found else None


def rewrite_slug_url(url: str, target: date) -> str:
    """
    If a URL contains a date slug like '5_april_2026', rewrite it to use
    the *target* date.  Preserves the separator character (_ or -).

    Returns the original URL unchanged if no slug date is found.
    """
    first = _first_slug_date_match(url)
    if not first:
        return url
    match, _orig = first

    # Determine the separator used in the original slug.
    # Use the character just before the month group (group 2) to correctly
    # handle ordinal suffixes like "5th-April-2026" where group 1 is "5".
    sep_pos = match.start(2) - 1
    sep = url[sep_pos] if 0 <= sep_pos < len(url) else "_"
    year_token = str(target.year) if len(match.group(3)) == 4 else f"{target.year % 100:02d}"

    new_slug = f"{target.day}{sep}{_MONTH_NAMES[target.month]}{sep}{year_token}"
    return url[: match.start()] + new_slug + url[match.end() :]


_WIX_COPY_OF_PREFIX = "copy-of-"
_DROPFILES_SEF_RE = re.compile(
    r"(?P<origin>https?://[^/]+)/files/(?P<catid>\d+)/"
    r"(?:Newsletters|Weekly-Bulletins|Bulletins)/(?P<fid>\d+)/",
    re.IGNORECASE,
)


def _strip_wix_copy_of_prefix(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    leaf = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    if leaf.lower().startswith(_WIX_COPY_OF_PREFIX):
        new_leaf = leaf[len(_WIX_COPY_OF_PREFIX) :]
        new_path = path[: path.rstrip("/").rfind(leaf)] + new_leaf
        if path.endswith("/"):
            new_path += "/"
        return parsed._replace(path=new_path).geturl()
    return url


def _with_wix_copy_of_prefix(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    leaf = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    if not leaf or leaf.lower().startswith(_WIX_COPY_OF_PREFIX):
        return url
    new_path = path[: path.rstrip("/").rfind(leaf)] + _WIX_COPY_OF_PREFIX + leaf
    if path.endswith("/"):
        new_path += "/"
    return parsed._replace(path=new_path).geturl()


def wix_dated_slug_candidates(
    example_url: str,
    target: date,
    *,
    weeks_back: int = 3,
) -> list[str]:
    """Rewrite a Wix dated page slug for *target* and prior Sundays.

    Wix often publishes a duplicated bulletin as ``copy-of-<original-slug>``
    when the editor copies last week's page (Ballinascreen 16/08/2026).
    Each week tries the canonical slug first, then the copy-of- variant.
    """
    example_url = (example_url or "").strip()
    if not example_url:
        return []
    seen: list[str] = []

    def _add(url: str) -> None:
        url = (url or "").strip()
        if url and url not in seen:
            seen.append(url)

    for i in range(weeks_back + 1):
        week = target - timedelta(days=7 * i)
        rewritten = rewrite_date_url(example_url, week)
        canonical = _strip_wix_copy_of_prefix(rewritten)
        _add(canonical)
        _add(_with_wix_copy_of_prefix(canonical))
    return seen


def predicted_wordpress_dated_post_urls(
    example_url: str,
    target: date,
    *,
    weeks_back: int = 3,
    post_days_before: tuple[int, ...] = (3, 2, 4, 1, 5, 6),
) -> list[str]:
    """Guess WordPress permalinks where slug Sunday ≠ /YYYY/MM/DD/ post date.

    St Teresa's (and similar) posts look like::

        /2026/08/06/the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/

    The leaf date is the bulletin Sunday; the folder date is when they hit
    Publish (usually 2–4 days earlier). ``rewrite_date_url`` would keep the
    old folder day and invent a 404 such as ``/2026/08/06/…-16th-august-2026/``.
    This helper rewrites the Sunday slug and tries a small range of post
    dates for this Sunday, then previous Sundays.
    """
    example_url = (example_url or "").strip()
    if not example_url:
        return []
    parsed = urlparse(example_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    leaf = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    first_slug = _first_slug_date_match(leaf)
    if not first_slug:
        return []
    slug_m, _slug_date = first_slug
    prefix = leaf[: slug_m.start()]
    suffix = leaf[slug_m.end() :]
    origin = f"{parsed.scheme}://{parsed.netloc}"
    seen: list[str] = []

    def _add(url: str) -> None:
        if url and url not in seen:
            seen.append(url)

    for i in range(weeks_back + 1):
        week = target - timedelta(days=7 * i)
        day_str = f"{week.day}{_ordinal_suffix(week.day)}"
        month_str = _MONTH_NAMES[week.month]
        slug = f"{prefix}{day_str}-{month_str}-{week.year}{suffix}"
        for offset in post_days_before:
            posted = week - timedelta(days=offset)
            _add(
                f"{origin}/{posted.year}/{posted.month:02d}/"
                f"{posted.day:02d}/{slug}/"
            )
    return seen


def dropfiles_task_download_url(example_url: str) -> str | None:
    """Convert a Dropfiles SEF ``/files/{catid}/Newsletters/{id}/…`` href.

    Some SiteGround hosts 403 the pretty URL but still serve
    ``index.php?option=com_dropfiles&task=frontfile.download&catid=&id=``
    (Banagher, confirmed 19/08/2026).
    """
    m = _DROPFILES_SEF_RE.search(example_url or "")
    if not m:
        return None
    return (
        f"{m.group('origin')}/index.php?option=com_dropfiles"
        f"&task=frontfile.download&catid={m.group('catid')}&id={m.group('fid')}"
    )


def rewrite_wp_url(url: str, target: date) -> str:
    """
    Rewrite a WordPress-style URL by updating both the ``YYYY/MM`` path
    component *and* any date slug in the filename (e.g. ``DD-Month-YYYY``).

    Examples::

        /wp-content/uploads/2026/03/29-March-2026.pdf
        → /wp-content/uploads/2026/04/5-April-2026.pdf   (target = 2026-04-05)

        /wp-content/uploads/2026/04/Newsletter-12-April-2026-1.pdf
        → /wp-content/uploads/2026/04/Newsletter-19-April-2026-1.pdf  (target = 2026-04-19)

    Returns the original URL unchanged if neither pattern is found.
    """
    # First update the date slug in the filename part
    new_url = rewrite_slug_url(url, target)

    # Then update the YYYY/MM path segment
    def _replace_ym(m: re.Match) -> str:
        try:
            orig_year = int(m.group(1))
            # Allow ±1 year to handle year-boundary transitions
            # (e.g. a December bulletin URL used to predict a January one)
            if abs(orig_year - target.year) <= 1:
                return f"/{target.year}/{target.month:02d}/"
        except (ValueError, AttributeError):
            pass
        return m.group(0)

    return _WP_YEAR_MONTH_RE.sub(_replace_ym, new_url)


def date_variants(target: date) -> list[str]:
    """
    Return all date-string patterns for the target date and the preceding six
    days that we should look for in PDF filenames / link text.
    """
    variants: list[str] = []
    for delta in range(7):
        d = target - timedelta(days=delta)
        dd = f"{d.day:02d}"
        mm = f"{d.month:02d}"
        yy = f"{d.year % 100:02d}"
        yyyy = str(d.year)
        variants += [
            f"{dd}{mm}{yy}",          # DDMMYY
            f"{dd}{mm}{yyyy}",        # DDMMYYYY
            f"{yyyy}-{mm}-{dd}",      # YYYY-MM-DD
            f"{yyyy}{mm}{dd}",        # YYYYMMDD
        ]
    return variants


def generate_url_variants(original_url: str, target_date: date) -> list[str]:
    """
    Generate alternative URLs by substituting *target_date* using every
    supported date-format pattern.

    Used by the pattern detector to recover from HTTP 404 responses caused
    by parish websites changing their URL date format.

    The function:
    1. Detects which date token is present in the URL (patterns A–E).
    2. Generates a replacement string for each other format.
    3. Returns up to 10 unique alternative URLs (excluding the original).

    Returns an empty list when no recognisable date is found.
    """
    parsed = urlparse(original_url)
    path = unquote(parsed.path)

    matched_token: str | None = None

    # Try DDMMYYYY (8 consecutive digits) — Pattern A'
    for m in _DDMMYYYY_RE.finditer(path):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if abs((d - target_date).days) < 14:
                matched_token = m.group(0)
                break
        except ValueError:
            pass

    # Try DDMMYY (6 consecutive digits) — Pattern A
    if matched_token is None:
        for m in _DDMMYY_RE.finditer(path):
            try:
                d = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
                if abs((d - target_date).days) < 14:
                    matched_token = m.group(0)
                    break
            except ValueError:
                pass

    # Try ISO YYYY-MM-DD — Pattern C
    if matched_token is None:
        for m in _ISO_RE.finditer(path):
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if abs((d - target_date).days) < 14:
                    matched_token = m.group(0)
                    break
            except ValueError:
                pass

    # Try D-M-YY (dashed) — Pattern B
    if matched_token is None:
        for m in _D_M_YY_RE.finditer(path):
            try:
                d = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
                if abs((d - target_date).days) < 14:
                    matched_token = m.group(0)
                    break
            except ValueError:
                pass

    # Try DD-Month-YYYY slug — Pattern D
    if matched_token is None:
        for m in _SLUG_DATE_RE.finditer(path):
            d = _date_from_slug_match(m)
            if d and abs((d - target_date).days) < 14:
                matched_token = m.group(0)
                break

    # Try [YYYY-M-D] bracketed — Pattern E
    if matched_token is None:
        for m in _BRACKETED_ISO_RE.finditer(path):
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if abs((d - target_date).days) < 14:
                    matched_token = m.group(0)
                    break
            except ValueError:
                pass

    if matched_token is None:
        return []

    td = target_date
    dd = f"{td.day:02d}"
    d_str = str(td.day)
    mm = f"{td.month:02d}"
    m_str = str(td.month)
    yy = f"{td.year % 100:02d}"
    yyyy = str(td.year)
    month_name = _MONTH_NAMES[td.month].capitalize()

    format_candidates = [
        f"{dd}{mm}{yy}",                       # A:  DDMMYY
        f"{dd}{mm}{yyyy}",                     # A': DDMMYYYY
        f"{yyyy}-{mm}-{dd}",                   # C:  YYYY-MM-DD
        f"{d_str}-{m_str}-{yy}",               # B:  D-M-YY
        f"{dd}-{month_name}-{yyyy}",           # D:  DD-Month-YYYY
        f"[{yyyy}-{m_str}-{d_str}]",           # E:  [YYYY-M-D]
    ]

    _MAX_VARIANTS = 10
    variants: list[str] = []
    seen = {original_url}

    for fmt in format_candidates:
        if len(variants) >= _MAX_VARIANTS:
            break
        new_path = path.replace(matched_token, fmt, 1)
        if new_path == path:
            continue
        new_url = parsed._replace(path=new_path).geturl()
        if new_url not in seen:
            variants.append(new_url)
            seen.add(new_url)

    return variants


def rewrite_date_url(url: str, target: date) -> str:
    """
    Rewrite a URL's date component(s) to use the *target* date.

    Recognised patterns (tried in order; first match wins):

    - Pattern A (DDMMYYYY / DDMMYY): /pdf/050426.pdf  ->  /pdf/120426.pdf
    - Pattern C (ISO YYYY-MM-DD):    /2026/04/2026-04-05.pdf  ->  /2026/04/2026-04-12.pdf
                                     (also updates any /YYYY/MM/ directory segment)
    - Pattern B (D-M-YY):            /onewebmedia/5-4-26.pdf  ->  /onewebmedia/12-4-26.pdf
    - Pattern D (DD-Month-YYYY):     Newsletter-12-April-2026.pdf  ->  Newsletter-19-April-2026.pdf
                                     (also updates any /YYYY/MM/ directory segment)
    - Pattern E ([YYYY-M-D]):        [2026-4-5].pdf  ->  [2026-4-12].pdf

    Returns the original URL unchanged if no date pattern is detected (Pattern F -
    static files like laveyparishbulletin.pdf are downloaded as-is).
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)

    def _update_yyyymm_dir(old_d: date, p: str) -> str:
        """Replace /YYYY/MM/ directory segments matching *old_d* with the target.

        WordPress's uploads folder is the *upload* month, which can differ
        from the bulletin's own filename date (e.g. a bulletin dated
        "29-March-2026" uploaded a few days later lands in .../2026/04/, not
        .../2026/03/) — an exact-match replace on the filename's own date
        would silently no-op and leave next week's guess in the wrong
        month's folder forever. Fall back to rewriting whatever /YYYY/MM/
        segment is actually present (within a year of target, to avoid
        touching unrelated numeric path segments) when the exact match
        fails (found 2026-08-10, bellaghyparish: filename said March but
        the uploads folder was already /2026/04/).
        """
        old_seg = f"/{old_d.year}/{old_d.month:02d}/"
        new_seg = f"/{target.year}/{target.month:02d}/"
        replaced = p.replace(old_seg, new_seg)
        if replaced != p:
            return replaced

        def _replace_any_ym(m: re.Match) -> str:
            try:
                if abs(int(m.group(1)) - target.year) <= 1:
                    return new_seg
            except ValueError:
                pass
            return m.group(0)

        return _WP_YEAR_MONTH_RE.sub(_replace_any_ym, p)

    # ------------------------------------------------------------------
    # Pattern A: DDMMYYYY (8 consecutive digits)
    # ------------------------------------------------------------------
    orig_ddmmyyyy: date | None = None

    def _replace_ddmmyyyy(m: re.Match) -> str:
        nonlocal orig_ddmmyyyy
        try:
            orig = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                if orig_ddmmyyyy is None:
                    orig_ddmmyyyy = orig
                return f"{target.day:02d}{target.month:02d}{target.year}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _DDMMYYYY_RE.sub(_replace_ddmmyyyy, path)
    if new_path != path:
        if orig_ddmmyyyy is not None:
            new_path = _update_yyyymm_dir(orig_ddmmyyyy, new_path)
        return parsed._replace(path=new_path).geturl()

    # Pattern A: DDMMYY (6 consecutive digits)
    orig_ddmmyy: date | None = None

    def _replace_ddmmyy(m: re.Match) -> str:
        nonlocal orig_ddmmyy
        try:
            year = 2000 + int(m.group(3))
            orig = date(year, int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                if orig_ddmmyy is None:
                    orig_ddmmyy = orig
                return f"{target.day:02d}{target.month:02d}{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _DDMMYY_RE.sub(_replace_ddmmyy, path)
    if new_path != path:
        if orig_ddmmyy is not None:
            new_path = _update_yyyymm_dir(orig_ddmmyy, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern C: ISO YYYY-MM-DD (with optional /YYYY/MM/ directory update)
    # ------------------------------------------------------------------
    orig_iso: "date | None" = None
    iso_m = _ISO_RE.search(path)
    if iso_m:
        try:
            orig_iso = date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            pass

    if orig_iso and abs((orig_iso - target).days) < 365:
        def _replace_iso(m: re.Match) -> str:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if abs((d - target).days) < 365:
                    return f"{target.year}-{target.month:02d}-{target.day:02d}"
            except ValueError:
                pass
            return m.group(0)

        new_path = _ISO_RE.sub(_replace_iso, path)
        new_path = _update_yyyymm_dir(orig_iso, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern B: D-M-YY (dashed, 1-2 digit day/month, 2-digit year)
    # e.g. 5-4-26  ->  12-4-26  (Limavady / Claudy, unpadded)
    #      16-08-26 -> 23-08-26 (Lisburn Blaris, keep zero-padding)
    # Day and month keep the source width so 16-08-26 is not rewritten
    # to 16-8-26 (that 404s). Year uses :02d so 2005 stays "05".
    # ------------------------------------------------------------------
    def _replace_d_m_yy(m: re.Match) -> str:
        try:
            year = 2000 + int(m.group(3))
            orig = date(year, int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                day_s, month_s = m.group(1), m.group(2)
                # 16-08-26 (both parts 2 digits) keeps zeros. 12-4-26 / 21-6-26
                # is the unpadded OneWeb style even when the day is already 10+.
                padded = len(day_s) == 2 and len(month_s) == 2
                day_fmt = f"{target.day:02d}" if padded else str(target.day)
                month_fmt = f"{target.month:02d}" if padded else str(target.month)
                return f"{day_fmt}-{month_fmt}-{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    orig_d_m_yy: date | None = None

    def _replace_d_m_yy_tracked(m: re.Match) -> str:
        nonlocal orig_d_m_yy
        replaced = _replace_d_m_yy(m)
        if replaced != m.group(0) and orig_d_m_yy is None:
            try:
                orig_d_m_yy = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
        return replaced

    new_path = _D_M_YY_RE.sub(_replace_d_m_yy_tracked, path)
    if new_path != path:
        if orig_d_m_yy is not None:
            new_path = _update_yyyymm_dir(orig_d_m_yy, new_path)
        return parsed._replace(path=new_path).geturl()

    def _replace_d_m_yy_dot(m: re.Match) -> str:
        try:
            year = 2000 + int(m.group(3))
            orig = date(year, int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                return f"{target.day}.{target.month}.{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    orig_d_m_yy_dot: date | None = None

    def _replace_d_m_yy_dot_tracked(m: re.Match) -> str:
        nonlocal orig_d_m_yy_dot
        replaced = _replace_d_m_yy_dot(m)
        if replaced != m.group(0) and orig_d_m_yy_dot is None:
            try:
                orig_d_m_yy_dot = date(
                    2000 + int(m.group(3)), int(m.group(2)), int(m.group(1))
                )
            except ValueError:
                pass
        return replaced

    new_path = _D_M_YY_DOT_RE.sub(_replace_d_m_yy_dot_tracked, path)
    if new_path != path:
        if orig_d_m_yy_dot is not None:
            new_path = _update_yyyymm_dir(orig_d_m_yy_dot, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern D: DD-Month-YYYY slug (also updates /YYYY/MM/ dir)
    # e.g. Newsletter-12-April-2026.pdf  ->  Newsletter-19-April-2026.pdf
    # ------------------------------------------------------------------
    first_slug = _first_slug_date_match(path)
    slug_m = first_slug[0] if first_slug else None
    orig_slug: date | None = first_slug[1] if first_slug else None

    slug_has_full_year = bool(slug_m and len(slug_m.group(3)) == 4)
    slug_in_range = bool(orig_slug and abs((orig_slug - target).days) < 365)

    if orig_slug and orig_slug == target:
        return url

    if orig_slug and (slug_has_full_year or slug_in_range):
        def _replace_slug_d(m: re.Match) -> str:
            try:
                old_month_num = _MONTH_MAP.get(m.group(2).lower())
                if not old_month_num:
                    return m.group(0)
                year = _year_from_slug_digits(m.group(3))
                if year is None:
                    return m.group(0)
                d = date(year, old_month_num, int(m.group(1)))
                year_full = len(m.group(3)) == 4
                if year_full or abs((d - target).days) < 365:
                    # Use the character just before group 2 as separator to
                    # correctly handle ordinals like "5th-April" where group 1="5"
                    sep_pos = m.start(2) - 1
                    sep = path[sep_pos] if 0 <= sep_pos < len(path) else "-"
                    # Wix slugs use lowercase months with underscores (5_april_2026).
                    month_raw = m.group(2)
                    if sep == "_" or month_raw.islower():
                        month_str = _MONTH_NAMES[target.month]
                    else:
                        month_str = _MONTH_NAMES[target.month].capitalize()
                    had_ordinal = _slug_had_ordinal(m.group(0))
                    day_str = (
                        f"{target.day}{_ordinal_suffix(target.day)}"
                        if had_ordinal
                        else str(target.day)
                    )
                    return f"{day_str}{sep}{month_str}{sep}{target.year}"
            except ValueError:
                pass
            return m.group(0)

        new_path = _SLUG_DATE_RE.sub(_replace_slug_d, path)
        new_path = _update_yyyymm_dir(orig_slug, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern E: [YYYY-M-D] bracketed ISO variant (Greenlough parish)
    # e.g. [2026-4-5]  ->  [2026-4-12]
    # ------------------------------------------------------------------
    def _replace_bracketed(m: re.Match) -> str:
        try:
            orig = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if abs((orig - target).days) < 365:
                return f"[{target.year}-{target.month}-{target.day}]"
        except ValueError:
            pass
        return m.group(0)

    new_path = _BRACKETED_ISO_RE.sub(_replace_bracketed, path)
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern G: WordPress date-based post slug /YYYY/MM/DD/slug/
    # (e.g. clonleighparish.com/2026/04/03/strabane-newsletter-.../
    #   -> clonleighparish.com/2026/04/10/)
    # Strip the unpredictable slug and return the day-archive URL with
    # the date shifted by 7 days so the fetcher can find the new post.
    # ------------------------------------------------------------------
    g_m = _WP_DATE_POST_RE.search(path)
    if g_m:
        try:
            g_orig = date(int(g_m.group(1)), int(g_m.group(2)), int(g_m.group(3)))
            if abs((g_orig - target).days) < 365:
                predicted_date = g_orig + timedelta(days=7)
                new_seg = (
                    f"/{predicted_date.year}"
                    f"/{predicted_date.month:02d}"
                    f"/{predicted_date.day:02d}/"
                )
                return parsed._replace(path=path[: g_m.start()] + new_seg).geturl()
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Pattern H: yearless "28th-June" / "16th-Aug" (Tawnawilly, Milford)
    # ------------------------------------------------------------------
    yearless_m = _YEARLESS_SLUG_RE.search(path)
    if yearless_m:
        old_month = _MONTH_MAP.get(yearless_m.group(2).lower())
        if old_month:
            month_raw = yearless_m.group(2)
            had_ordinal = bool(re.search(r"(?:st|nd|rd|th)", yearless_m.group(0), re.I))
            sep_m = re.search(r"(?:st|nd|rd|th)?([_\-\s])", yearless_m.group(0), re.I)
            sep = sep_m.group(1) if sep_m else "-"
            month_full = _MONTH_NAMES[target.month]
            month_str = month_full[:3] if len(month_raw) <= 3 else month_full
            if month_raw.isupper():
                month_str = month_str.upper()
            elif month_raw[0].isupper():
                month_str = month_str.capitalize()
            day_str = (
                f"{target.day}{_ordinal_suffix(target.day)}"
                if had_ordinal
                else str(target.day)
            )
            new_frag = f"{day_str}{sep}{month_str}"
            new_path = path[: yearless_m.start()] + new_frag + path[yearless_m.end() :]
            return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern I: Month-DD-YY "Sunday-Sept-06-26.pdf" (Tawnawilly 2026-09-06)
    # ------------------------------------------------------------------
    month_first_m = _MONTH_DAY_YY_RE.search(path)
    if month_first_m:
        month_raw = month_first_m.group(1)
        day_raw = month_first_m.group(2)
        year_raw = month_first_m.group(3)
        month_names = _MONTH_NAME_VARIANTS.get(target.month, ())
        if target.month == 9:
            month_names = ("Sept", "Sep", "September")
        month_str = min(month_names, key=lambda n: abs(len(n) - len(month_raw))) if month_names else _MONTH_NAMES[target.month]
        if month_raw.isupper():
            month_str = month_str.upper()
        elif month_raw[0].isupper():
            month_str = month_str[0].upper() + month_str[1:]
        else:
            month_str = month_str.lower()
        day_str = f"{target.day:02d}" if len(day_raw) == 2 else str(target.day)
        year_str = f"{target.year % 100:02d}" if len(year_raw) == 2 else str(target.year)
        new_frag = f"{month_str}-{day_str}-{year_str}"
        new_path = path[: month_first_m.start()] + new_frag + path[month_first_m.end() :]
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern F: No date found - return URL unchanged (static files).
    # However, if the URL has a /YYYY/MM/ directory segment, update that
    # even when the filename itself has no recognisable date.  This handles
    # WordPress image bulletins (e.g. Iskaheen parish) where the filename
    # is always "1.jpg" but the year/month directory changes monthly.
    # ------------------------------------------------------------------
    new_path = _WP_YEAR_MONTH_RE.sub(
        lambda m: (
            f"/{target.year}/{target.month:02d}/"
            if abs(int(m.group(1)) - target.year) <= 1
            else m.group(0)
        ),
        path,
    )
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    return url


def oneweb_newsletter_download_urls(example_url: str, target: date) -> list[str]:
    """
    Direct onewebmedia newsletter URLs for One.com parishes (e.g. Claudy).

    Skips slow Google Docs viewer iframes — downloads the .docx file directly.
    Tries filename quirks seen on parishofclaudy.com (extra spaces before .docx).
    """
    primary = rewrite_date_url(example_url, target)
    parsed = urlparse(primary)
    path = unquote(parsed.path)
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        u = (url or "").strip()
        if u and u not in seen:
            seen.add(u)
            candidates.append(u)

    _add(primary)
    newsletter_match = re.search(
        r"(?i)(/onewebmedia/)(newsletter\s+\d{1,2}-\d{1,2}-\d{2})",
        path,
    )
    if newsletter_match:
        prefix, stem = newsletter_match.group(1), newsletter_match.group(2)
        for suffix in (".docx", " .docx", " -.docx"):
            variant_path = f"{prefix}{stem}{suffix}"
            _add(parsed._replace(path=quote(variant_path, safe="/")).geturl())
    elif primary.lower().endswith(".docx"):
        stem = primary[:-5]
        _add(stem + " .docx")
        _add(stem + " -.docx")

    return candidates


# ---------------------------------------------------------------------------
# Pattern H — Sequential newsletter number (Banagher & Three Patrons)
# ---------------------------------------------------------------------------

# Matches /Newsletters/NNN/ (Banagher), /Weekly-Bulletins/NNN/ (Three Patrons),
# and /Bulletins/NNN/ (Port Glenone Dropfiles).
_NEWSLETTER_NUM_RE = re.compile(r"(/(?:Newsletters|Weekly-Bulletins|Bulletins)/)(\d+)/")


def extract_newsletter_number(url: str) -> "int | None":
    """
    Extract the sequential newsletter number from a Banagher-, Three-Patrons-,
    or Port-Glenone-style URL.

    Examples::

        https://www.banagherparish.com/files/9/Newsletters/384/Bulletin---...
        → 384

        https://www.threepatrons.org/files/10/Weekly-Bulletins/95/Sunday-12th-April-2026
        → 95

        https://stmarysportglenone.org/download/9/Bulletins/109/17th-SUNDAY-IN-ORDINARY-TIME
        → 109

    Returns ``None`` if no matching ``/.../NNN/`` segment is found.
    """
    m = _NEWSLETTER_NUM_RE.search(url)
    if m:
        return int(m.group(2))
    return None


def rewrite_newsletter_number_url(url: str, increment: int = 1) -> str:
    """
    Increment the sequential newsletter number in a Banagher- or Three-Patrons-style
    URL and strip the unpredictable free-form slug that follows it.

    Examples::

        https://www.banagherparish.com/files/9/Newsletters/384/Bulletin---Divine-Mercy-Sunday---12th-April-2026
        → https://www.banagherparish.com/files/9/Newsletters/385/

        https://www.threepatrons.org/files/10/Weekly-Bulletins/95/Sunday-12th-April-2026
        → https://www.threepatrons.org/files/10/Weekly-Bulletins/96/

    The slug after the number is removed because it cannot be predicted.

    Returns the original URL unchanged if no ``/Newsletters/NNN/``,
    ``/Weekly-Bulletins/NNN/``, or ``/Bulletins/NNN/`` segment is found.
    """
    m = _NEWSLETTER_NUM_RE.search(url)
    if not m:
        return url
    new_number = int(m.group(2)) + increment
    # m.group(1) preserves the category name (/Newsletters/ or /Weekly-Bulletins/)
    return url[: m.start()] + m.group(1) + f"{new_number}/"


def rewrite_newsletter_number_for_target(url: str, target: date) -> str:
    """
    Advance a Pattern H bulletin number by whole weeks between the example slug date
    and *target* (harvest Sunday).

    Falls back to +1 increment when no date can be parsed from the example URL.
    """
    m = _NEWSLETTER_NUM_RE.search(url)
    if not m:
        return url
    base_number = int(m.group(2))
    path = unquote(urlparse(url).path)
    slug = path.split("/")[-1] if path else ""
    ref_date = extract_date_from_slug(slug) or extract_date_from_string(slug)
    if ref_date:
        weeks = (target - ref_date).days // 7
        new_number = base_number + max(0, weeks)
    else:
        new_number = base_number + 1
    return url[: m.start()] + m.group(1) + f"{new_number}/"


def dropfiles_liturgical_slug(target: date) -> str | None:
    """
    Port Glenone / Three Patrons Dropfiles title slug for *target* Sunday.

    Example: 18th_Sunday_in_Ordinary_Time → 18th-SUNDAY-IN-ORDINARY-TIME
    """
    from .liturgical import get_liturgical_name

    name = get_liturgical_name(target)
    if not name:
        return None
    parts = [p for p in name.split("_") if p]
    if not parts:
        return None
    # Keep ordinal head (18th / 1st / 2nd / 3rd); upper-case the rest like the live site.
    head = parts[0]
    rest = "-".join(p.upper() for p in parts[1:])
    return f"{head}-{rest}" if rest else head.upper()


def predict_dropfiles_bulletin_urls(
    example_url: str,
    target: date,
    *,
    id_window: int = 3,
) -> list[str]:
    """
    Build resilient Dropfiles download URL candidates from a known example href.

    Tries liturgical title slugs across a small sequential file-ID window so harvest
    still works when the listing page is empty or blocked.
    """
    example_url = (example_url or "").strip()
    if not example_url:
        return []
    m = _NEWSLETTER_NUM_RE.search(example_url)
    if not m:
        return []

    prefix = example_url[: m.start()] + m.group(1)
    example_num = int(m.group(2))
    rewritten = rewrite_newsletter_number_for_target(example_url, target)
    predicted_num = extract_newsletter_number(rewritten) or (example_num + 1)
    slug = dropfiles_liturgical_slug(target)

    nums: list[int] = []
    for n in (
        predicted_num,
        example_num,
        predicted_num + 1,
        example_num + 1,
        predicted_num - 1,
        example_num - 1,
    ):
        if n is None or n < 1:
            continue
        if n not in nums:
            nums.append(n)
        if len(nums) >= id_window + 2:
            break

    # Expand a contiguous window around the best guess.
    center = predicted_num or example_num
    for n in range(center - id_window, center + id_window + 1):
        if n >= 1 and n not in nums:
            nums.append(n)

    out: list[str] = []
    seen: set[str] = set()
    for num in nums:
        candidates = []
        if slug:
            candidates.append(f"{prefix}{num}/{slug}")
        candidates.append(f"{prefix}{num}/")
        for url in candidates:
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


def safe_filename(prefix: str, suffix: str) -> str:
    """Combine a sanitized parish prefix with a file suffix."""
    prefix = re.sub(r"[^a-z0-9_-]", "_", prefix.lower())
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# Greenlough parish — liturgical name + date rewrite
# ---------------------------------------------------------------------------

_ORDINARY_TIME_LEAF_RE = re.compile(
    r"(?i)^.+-Sunday-(?:in|of)-Ordinary-Time\.pdf$"
)


def rewrite_ordinary_time_upload_url(url: str, target: date) -> str | None:
    """Rewrite Nth-Sunday-in-Ordinary-Time.pdf to this harvest Sunday's name.

    Loughshore (and Holy Family) name the weekly file after the liturgical
    Sunday and put it in /uploads/YYYY/MM/. Date-only rewrite left
    21st-Sunday-in-Ordinary-Time.pdf in September and 404'd (found 2026-09-06).
    """
    parsed = urlparse(url)
    path = unquote(parsed.path or "")
    if "/" not in path:
        return None
    directory, leaf = path.rsplit("/", 1)
    if not _ORDINARY_TIME_LEAF_RE.match(leaf):
        return None
    from .liturgical import get_liturgical_name

    name = get_liturgical_name(target)
    if not name or "Ordinary_Time" not in name:
        return None
    new_leaf = name.replace("_", "-") + ".pdf"
    if re.search(r"(?i)-Sunday-of-Ordinary-Time\.pdf$", leaf):
        new_leaf = new_leaf.replace("-Sunday-in-", "-Sunday-of-")
    new_dir = re.sub(
        r"/\d{4}/\d{2}$",
        f"/{target.year}/{target.month:02d}",
        directory,
    )
    return parsed._replace(path=f"{new_dir}/{new_leaf}").geturl()


def rewrite_greenlough_url(url: str, target: date) -> str | None:
    """
    Rewrite a Greenlough parish URL by replacing both the liturgical
    Sunday name and the [YYYY-M-D] date bracket.

    Returns the new URL, or None if this isn't a Greenlough URL or
    no liturgical name is available for the target date.
    """
    if "greenlough.com/publications/newsletter/" not in url:
        return None
    from .liturgical import get_liturgical_name
    name = get_liturgical_name(target)
    if not name:
        return None
    # The URL pattern is: .../newsletter/LITURGICAL_NAME_[YYYY-M-D].pdf
    # Extract the base and rebuild
    base = url.split("/newsletter/")[0] + "/newsletter/"
    return f"{base}{name}_[{target.year}-{target.month}-{target.day}].pdf"


# ---------------------------------------------------------------------------
# Clonleigh parish — WordPress post URL prediction
# ---------------------------------------------------------------------------

_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    """Return ordinal string for *n* (e.g. 12 → '12th', 1 → '1st')."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIXES.get(n % 10, 'th')}"


def rewrite_clonleigh_url(target: date) -> str:
    """
    Predict the Clonleigh (Strabane Pastoral Area) newsletter WordPress post URL.

    The newsletter is published on the Saturday before the target Sunday.
    Slug format: strabane-pastoral-area-newsletter-for-sunday-DDth-month-YYYY

    Example for target 2026-04-19 (Sunday):
        published: 2026-04-18 (Saturday)
        → https://clonleighparish.com/2026/04/18/strabane-pastoral-area-newsletter-for-sunday-19th-april-2026/
    """
    post_date = target - timedelta(days=1)  # Saturday
    day_ord = _ordinal(target.day)
    month_lower = _MONTH_NAMES[target.month]
    slug = (
        f"strabane-pastoral-area-newsletter-for-sunday-"
        f"{day_ord}-{month_lower}-{target.year}"
    )
    return (
        f"https://clonleighparish.com"
        f"/{post_date.year}/{post_date.month:02d}/{post_date.day:02d}/{slug}/"
    )


def _naomhfionan_first_counted_sunday(year: int) -> date:
    """First Sunday counted as newsletter #1 for *year*.

    Normally the first Sunday on/after Jan 1. Confirmed exception: when Jan 1
    itself falls on a Sunday (e.g. 2023), the parish's own numbering skips
    New Year's Day and starts counting from the following Sunday instead —
    verified against real archived filenames (Newsletter-1-For-BapSunA on
    8 Jan 2023, not 1 Jan 2023).
    """
    jan1 = date(year, 1, 1)
    if jan1.weekday() == 6:
        return jan1 + timedelta(days=7)
    return jan1 + timedelta(days=(6 - jan1.weekday()) % 7)


def naomhfionan_newsletter_number(target: date) -> int:
    """Predict naomhfionan.com's own sequential newsletter number for *target*.

    Pattern reverse-engineered 2026-08-10 from ~50 real historical filenames
    (naomhfionan.com/wp-content/uploads/.../Parish-Newsletter-N-for-...pdf)
    pulled from the Wayback Machine CDX index, spanning 2022-2026: N is
    simply the number of full weeks between *target* and the first Sunday
    counted that calendar year, +1. Verified exact matches (no drift) across
    12 independent data points in 2024, 2025 and 2026 (the numbering resets
    each 1 January, independent of the Advent/liturgical-year boundary).
    """
    epoch = _naomhfionan_first_counted_sunday(target.year)
    return (target - epoch).days // 7 + 1


def naomhfionan_bulletin_url(target: date, *, number_offset: int = 0) -> str:
    """Predict this Sunday's naomhfionan.com (Falcarragh) bulletin PDF URL.

    Filename shape confirmed live 2026-08-10:
    Parish-Newsletter-{number}-for-Sun-{cycle_letter}-{DDMMYYYY}.pdf under
    wp-content/uploads/{YYYY}/{MM}/ — an asset path NOT behind the site's
    Cloudflare Managed Challenge (only the HTML listing page at /nuachtlitir/
    is challenged). *number_offset* lets callers probe neighbouring numbers
    (+-1) as a fallback for the rare skipped-week edge cases seen in older
    filenames, without recomputing the whole prediction.
    """
    from .liturgical import liturgical_cycle_letter

    number = naomhfionan_newsletter_number(target) + number_offset
    letter = liturgical_cycle_letter(target)
    ddmmyyyy = target.strftime("%d%m%Y")
    filename = f"Parish-Newsletter-{number}-for-Sun-{letter}-{ddmmyyyy}.pdf"
    return f"https://naomhfionan.com/wp-content/uploads/{target.year}/{target.month:02d}/{filename}"


# ---------------------------------------------------------------------------
# Parish Press Uploader helpers
# ---------------------------------------------------------------------------

# Matches Parish Press Uploader storage URLs specifically (parishpress.net,
# under the fixed /wp-content/uploads/parish-bulletins/ path), which always
# serve a single current file named exactly "bulletin.<ext>" per parish (any
# query string, e.g. a "?t=<timestamp>" cache-buster, is preserved as a
# separate group). Deliberately scoped to this one host/path rather than any
# URL ending in "bulletin.<ext>" — plenty of unrelated parish sites also name
# their weekly file bulletin.pdf, and those must not be affected.
# The uploader's own client-side JS already merges multiple photos into one
# multi-page bulletin.pdf via pdf-lib before upload, and only a Word document
# (.doc/.docx) is ever stored unconverted — so the harvester side only needs
# to know which filename to try each week, not how to build a PDF from a
# batch of separate images.
_PARISH_UPLOADER_BULLETIN_RE = re.compile(
    r"^(?P<base>https?://(?:www\.)?parishpress\.net/wp-content/uploads/"
    r"parish-bulletins/[^?]*/bulletin)\.(?P<ext>pdf|docx|doc|jpe?g|png)(?P<query>\?.*)?$",
    re.IGNORECASE,
)

# Try the most common/expected format first (pdf), then the two upload
# formats the harvester already knows how to convert to PDF.
PARISH_UPLOADER_EXT_PRIORITY: tuple[str, ...] = ("pdf", "docx", "doc", "jpg", "jpeg", "png")


def is_parish_uploader_bulletin_url(url: str) -> bool:
    """Return True if *url* points at a Parish Press Uploader ``bulletin.<ext>`` file."""
    return bool(_PARISH_UPLOADER_BULLETIN_RE.match((url or "").strip()))


def parish_uploader_bulletin_candidates(url: str) -> list[str]:
    """Build the ordered list of ``bulletin.<ext>`` URLs to try for a Parish Press Uploader parish.

    The parish secretary might upload a PDF one week and a Word document or a
    single photo the next — whichever they last uploaded is the only file
    that exists on the server, so the harvester must try every supported
    extension rather than assuming ``bulletin.pdf`` is always there. Returns
    ``[]`` if *url* is not a recognised uploader bulletin URL.
    """
    match = _PARISH_UPLOADER_BULLETIN_RE.match((url or "").strip())
    if not match:
        return []
    base = match.group("base")
    matched_ext = match.group("ext").lower()
    ordered_exts = [matched_ext] + [
        ext for ext in PARISH_UPLOADER_EXT_PRIORITY if ext != matched_ext
    ]
    cache_bust = int(time.time())
    return [f"{base}.{ext}?t={cache_bust}" for ext in ordered_exts]


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def is_valid_pdf(path: Path) -> bool:
    """Return True if the file at *path* starts with the PDF magic bytes ``%PDF``."""
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"%PDF"
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Permanent ParishPress bulletin paths + MCN.live newsletter JSON
# ---------------------------------------------------------------------------

_PERMANENT_BULLETIN_PATH_RE = re.compile(
    r"^/bulletin/[a-z0-9_-]+/[a-z0-9._-]+/?$",
    re.IGNORECASE,
)
_MCN_CHURCH_ID_RE = re.compile(
    r'id=["\']hfChurchId["\'][^>]*value=["\'](\d+)["\']'
    r'|value=["\'](\d+)["\'][^>]*id=["\']hfChurchId["\']',
    re.IGNORECASE,
)


def looks_like_permanent_bulletin_url(url: str) -> bool:
    """True for always-current ParishPress paths that redirect to this week's file.

    Example: https://newtownkilleaparish.ie/bulletin/raphoe/newtown-killea/
    Do not treat the listing page /bulletin/ as permanent — that 403s bots.
    """
    raw = unquote((url or "").strip())
    if not raw.lower().startswith(("http://", "https://")):
        return False
    path = urlparse(raw).path.rstrip("/") + "/"
    if _PERMANENT_BULLETIN_PATH_RE.match(path.rstrip("/") + "/" if not path.endswith("/") else path):
        return True
    lower_path = urlparse(raw.lower()).path
    return "/parish-bulletins/" in lower_path and lower_path.endswith("bulletin.pdf")


def extract_mcn_church_id(html: str) -> str | None:
    """Read hidden ``hfChurchId`` from an MCN.live camera page."""
    match = _MCN_CHURCH_ID_RE.search(html or "")
    if not match:
        return None
    return match.group(1) or match.group(2) or None


def mcn_profile_data_url(camera_page_url: str, church_id: str | int) -> str:
    """Build POST URL for ``/Website/ProfileDataByJson/{churchId}``."""
    parsed = urlparse((camera_page_url or "").strip())
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://mcn.live"
    return f"{origin}/Website/ProfileDataByJson/{int(church_id)}"


def mcn_newsletter_url_from_profile(payload: dict | None) -> str | None:
    """Return ``newsletter.newsLetterUrl`` from an MCN ProfileDataByJson body."""
    if not isinstance(payload, dict):
        return None
    newsletter = payload.get("newsletter")
    if not isinstance(newsletter, dict):
        return None
    url = str(newsletter.get("newsLetterUrl") or "").strip()
    if url.lower().startswith(("http://", "https://")):
        return url
    return None


_CHURCHMEDIA_RESERVED_PATHS = {
    "api",
    "newsletter",
    "assets",
    "embed",
    "video",
    "videos",
    "login",
    "auth",
    "admin",
    "dashboard",
}
_CHURCHMEDIA_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,80}$")


def churchmedia_slug_from_url(url: str) -> str | None:
    """Return the public channel slug from a churchmedia.tv listing URL.

    ``https://churchmedia.tv/st-patricks-church-2`` → ``st-patricks-church-2``.
    Newsletter PDF paths and ``/api/`` URLs are not slugs.
    """
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "churchmedia.tv":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    slug = parts[0]
    if slug.lower() in _CHURCHMEDIA_RESERVED_PATHS:
        return None
    if not _CHURCHMEDIA_SLUG_RE.fullmatch(slug):
        return None
    return slug


def churchmedia_channel_about_url(slug: str) -> str:
    """Build GET URL for ``/api/getChannelAbout?slug=…``."""
    token = (slug or "").strip()
    return f"https://churchmedia.tv/api/getChannelAbout?slug={token}"


def churchmedia_newsletter_url_from_about(payload: dict | None) -> str | None:
    """Return the current newsletter PDF from a churchmedia getChannelAbout body.

    Strips ``?cb=`` cache-busters so callers never persist a dead token. The
    path token (``/newsletter/<id>.<slug>.pdf``) still changes on each upload
    and must be read live from the API.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    url = str(data.get("newsletter_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    parsed = urlparse(url)
    path = unquote(parsed.path or "")
    if "/newsletter/" not in path.lower() or not path.lower().endswith(".pdf"):
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
