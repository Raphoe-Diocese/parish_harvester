"""
bulletin_freshness.py — Stale bulletin detection and mega-PDF safety net.

When a downloaded PDF URL carries an explicit date outside the current harvest
week, the bulletin is rejected from the mega PDF and a retry strategy is
recorded for the crawler / operator.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import unquote

from .utils import (
    _is_within_opaque_hash,
    _opaque_hash_spans,
    extract_date_from_slug,
    extract_date_from_string,
    yearless_slug_date,
)

if TYPE_CHECKING:
    from .fetcher import FetchResult, ParishEntry

# Ahead-only grace: up to 8 calendar days after harvest target is still fresh.
MAX_STALE_DAYS_FROM_TARGET = 8
# Bulletin week window used by fetcher candidate scoring (Sun − 6 … target Sun).
WEEK_LOOKBACK_DAYS = 6

_RETRY_QUEUE_PATH = Path(__file__).resolve().parent.parent / "parishes" / "retry_queue.json"

# ISO and compact patterns (shared with harvest_log for consistency).
_DDMMYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")
_DDMMYYYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})((?:19|20)\d{2})(?!\d)")
_ISO_RE = re.compile(
    r"(?<!\d)(20\d{2})[-_/](0?[1-9]|1[0-2])[-_/](0?[1-9]|[12]\d|3[01])(?!\d)"
)
_DMY_ISO_RE = re.compile(
    r"(?<!\d)(0?[1-9]|[12]\d|3[01])[-_/](0?[1-9]|1[0-2])[-_/]((?:19|20)\d{2})(?!\d)"
)
# Matches the leading ordinal in "19th-Suday-in-ordinary-time...", "3rd-Sunday
# -of-Advent...", etc. — a liturgical Sunday-count, never a day-of-month. Must
# be followed by liturgical-season wording (not e.g. a month name) so genuine
# day-of-month filenames like "9th-August-2026.pdf" (antrimparish) aren't
# mistaken for a Sunday-count and lose their real day — that regression let
# antrimparish silently fall back to day=1 (2026-08-01 instead of 2026-08-09)
# Athlone letter-month weekly files: I-Sept2726.pdf / H-Aug3026.pdf / G-July2626.pdf
_ATHLONE_LETTER_MONTH_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:[a-z]-)?"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"(3[01]|[12]\d|0?[1-9])(\d{2})(?:\.pdf)?$",
    re.IGNORECASE,
)
_MONTH_NAME_TO_NUM = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
# and only "passed" by accident, via the 8-day grace window, rather than the
# correct in_bulletin_week match (found 2026-08-10 while auditing every
# grace-window "ok" for hidden freshness bugs).
_LEADING_ORDINAL_RE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)[\s_-]*(?:sun|suday|sunday|ordinary|advent|lent|easter|christmas)",
    re.I,
)

# Ballymote Page-01-3.jpg / page-04-3.jpg — digits are page numbers, not day
# (found 27/09/2026: page-04 dated as 04/09 and rejected as stale).
_PAGE_SCAN_BASENAME_RE = re.compile(r"^page[-_]?\d+", re.IGNORECASE)



FreshnessStatus = Literal["fresh", "stale", "unknown"]


@dataclass(frozen=True)
class FreshnessVerdict:
    status: FreshnessStatus
    extracted_date: date | None = None
    reason: str = ""
    days_from_target: int | None = None


def week_window(target: date) -> tuple[date, date]:
    """Return (week_start, week_end) for the harvest target Sunday."""
    return target - timedelta(days=WEEK_LOOKBACK_DAYS), target


def extract_bulletin_date(url_or_text: str) -> date | None:
    """Extract the most likely bulletin date from a URL or link label."""
    # Wix's `/_files/ugd/<hash>.docx?dn=<original filename>` pattern (and
    # similar CDNs) puts the human-readable, dated filename in a URL-encoded
    # query parameter, e.g. "?dn=Bulletin%207th%20June%202026.docx" — without
    # decoding, "%20" breaks the ordinal/month/year apart so no date pattern
    # (including the slug matcher below) can match it (found 2026-08-09,
    # parishofhannahstown, after replay.py started returning the real Wix
    # file URL instead of the listing page — see _download_source_url).
    text = unquote(url_or_text or "")

    # WordPress media folders are authoritative: /uploads/2026/06/file.pdf
    wp_uploads = re.search(r"/uploads/(20\d{2})/(0?\d{1,2})/", text, re.I)
    if wp_uploads:
        try:
            folder_year = int(wp_uploads.group(1))
            folder_month = int(wp_uploads.group(2))
            basename = text.rsplit("/", 1)[-1].lower()
            if re.search(r"sun.?ot|sunday|ordinary.?time", basename, re.I):
                bulletin_dm = re.search(r"bulletin(\d{2})(\d{2})", basename, re.I)
                if bulletin_dm:
                    day = int(bulletin_dm.group(1))
                    month = int(bulletin_dm.group(2))
                    if month == folder_month:
                        return _safe_date(folder_year, folder_month, day)
            # Bare YYYYMMDD filename with no separators at all, e.g.
            # "20260705.pdf" (kincasslagh.ie) — the WordPress upload
            # folder's own year/month are repeated verbatim as the
            # filename's leading digits, so read the day straight off the
            # trailing 2 digits. Without this the whole basename is one
            # contiguous 8-digit run with no isolated day-like substring for
            # day_match/day_match_4y/slug_day below to find, silently
            # falling through to the day=1 default (found 2026-08-10,
            # kincasslagh: misdated 20260705.pdf as 2026-07-01).
            yyyymmdd_match = re.match(
                rf"{folder_year}{folder_month:02d}(0[1-9]|[12]\d|3[01])$",
                basename.rsplit(".", 1)[0],
            )
            if yyyymmdd_match:
                day = int(yyyymmdd_match.group(1))
                return _safe_date(folder_year, folder_month, day)
            day_match = re.search(
                rf"(?<!\d)(0?[1-9]|[12]\d|3[01]){folder_month:02d}{folder_year % 100:02d}(?!\d)",
                basename,
            )
            if day_match:
                day = int(day_match.group(1))
                return _safe_date(folder_year, folder_month, day)
            # Same idea as day_match just above, but for a 4-digit year, e.g.
            # "Parish-Bulletin-09082026.pdf" (DDMMYYYY, contiguous digits).
            # Without this, the wp_uploads branch hard-returns via the day=1
            # fallback below before ever reaching the general _DDMMYYYY_RE
            # pattern later in this function, silently misdating a
            # perfectly well-formed DDMMYYYY filename as the 1st of the
            # month (found 2026-08-10, st-colmcilles: only "passed" by
            # accident via the grace-day window, not the correct
            # in_bulletin_week match).
            day_match_4y = re.search(
                rf"(?<!\d)(0?[1-9]|[12]\d|3[01]){folder_month:02d}{folder_year}(?!\d)",
                basename,
            )
            if day_match_4y:
                day = int(day_match_4y.group(1))
                return _safe_date(folder_year, folder_month, day)
            # ISO-dashed filename repeating the upload folder's own year/month,
            # e.g. "2026-07-26.pdf" (clonmanyparish.ie) inside .../uploads/2026/07/.
            # Without this, the generic slug_day fallback below finds "07" (the
            # MONTH segment, isolated by the hyphens on both sides) as the
            # leftmost 1-2 digit number in the string and returns it as if it
            # were the day-of-month — misdating this as the 7th instead of the
            # 26th (found 2026-08-10, clonmanyparish: reported "bulletin date
            # 2026-07-07" for a file plainly named 2026-07-26.pdf, wrongly
            # inflating how stale it looked).
            iso_dash_match = re.search(
                rf"{folder_year}-{folder_month:02d}-(0[1-9]|[12]\d|3[01])",
                basename,
            )
            if iso_dash_match:
                day = int(iso_dash_match.group(1))
                return _safe_date(folder_year, folder_month, day)
            # Filename-first: 16.8.26-20th-Sunday.pdf, 2026-August-16-…,
            # Twentieth-Sunday-in-Ordinary-Time.pdf. Must run before the
            # day=1 folder default — that default dated Holy Family's
            # current Twentieth-Sunday file as 01/08/2026 and rejected it
            # as 15 days stale against 16/08/2026 (found 2026-08-18).
            filename_date = extract_date_from_string(basename)
            if filename_date:
                return filename_date
            from .liturgical import liturgical_date_from_text

            liturgical = liturgical_date_from_text(basename, folder_year)
            if liturgical:
                return liturgical
            # UUID/hash scans (Iskaheen) have no day-of-month. Do not let
            # slug_day pick a hex digit out of the hash; freshness then
            # treats same-month hashes as current-month.
            if _opaque_hash_spans(basename):
                return _safe_date(folder_year, folder_month, 1)
            # "19th-Suday-in-ordinary-time-724x1024.png" style filenames lead
            # with the LITURGICAL Sunday-count ordinal (e.g. "19th Sunday in
            # Ordinary Time" — the 19th Sunday of the church year), not a
            # day-of-month, even though it's a 1-2 digit number that happens
            # to look like a valid day. The generic slug_day fallback below
            # was blindly treating that ordinal as the day, misdating this
            # filename as 2026-08-19 (10 days ahead of the actual 2026-08-09
            # target) and getting it wrongly rejected as stale (found
            # 2026-08-10, derriaghycatholicparish: the real content matched
            # "19th Sunday in Ordinary Time", which is genuinely correct for
            # 09/08/2026, but the filename's leading "19" isn't a date at
            # all). Skip slug_day when it matched that same leading ordinal.
            # Page-01 / page-04 scans: page index, not calendar day.
            if _PAGE_SCAN_BASENAME_RE.match(basename):
                return _safe_date(folder_year, folder_month, 1)
            ordinal_match = _LEADING_ORDINAL_RE.match(basename)
            slug_day = re.search(r"(?<!\d)(0?[1-9]|[12]\d|3[01])(?!\d)", basename)
            if slug_day and not (
                ordinal_match and slug_day.start(1) == ordinal_match.start(1)
            ):
                return _safe_date(folder_year, folder_month, int(slug_day.group(1)))
            # Athlone-style weekly files: I-Sept2726.pdf / H-Aug3026.pdf live
            # forever under /uploads/2024/11/. The folder year is not the
            # bulletin week — parse Month+Day+YY from the basename instead
            # (found 01/10/2026: folder day=1 → 2024-11-01 stale-rejected a
            # genuine 27/09/2026 PDF).
            letter_month = _ATHLONE_LETTER_MONTH_RE.search(basename)
            if letter_month:
                month = _MONTH_NAME_TO_NUM[letter_month.group(1).lower()]
                day = int(letter_month.group(2))
                year = 2000 + int(letter_month.group(3))
                parsed = _safe_date(year, month, day)
                if parsed:
                    return parsed
            # No day in the filename — do not invent the 1st of an old upload
            # folder (same Athlone trap). Fall through for body-text / unknown.
            return None
        except (TypeError, ValueError):
            pass

    basename = text.rsplit("/", 1)[-1]
    slug_source = basename.rsplit(".", 1)[0] if "." in basename else basename
    slug_date = extract_date_from_slug(slug_source)
    if slug_date:
        return slug_date

    parsed = extract_date_from_string(text)
    if parsed:
        return parsed

    from .liturgical import liturgical_date_from_text

    year_hint_match = re.search(r"/uploads/(20\d{2})/", text, re.I)
    year_hint = int(year_hint_match.group(1)) if year_hint_match else date.today().year
    liturgical = liturgical_date_from_text(text, year_hint)
    if liturgical:
        return liturgical

    patterns = (
        (_ISO_RE, lambda m: _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (_DMY_ISO_RE, lambda m: _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
        (_DDMMYY_RE, lambda m: _safe_parse_ddmmyy(m.group(1), m.group(2), m.group(3))),
        (_DDMMYYYY_RE, lambda m: _safe_parse("%d%m%Y", "".join(m.groups()))),
    )
    # Guard against opaque CDN hashes (Wix/Squarespace-style filenames) whose
    # random hex digits can coincidentally look like a DDMMYY/DDMMYYYY date.
    spans = _opaque_hash_spans(text)
    for pattern, parser in patterns:
        for match in pattern.finditer(text):
            if _is_within_opaque_hash(spans, match.start(), match.end()):
                continue
            result = parser(match)
            if result:
                return result
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _safe_parse(fmt: str, raw: str) -> date | None:
    try:
        return datetime.strptime(raw, fmt).date()
    except ValueError:
        return None


def _safe_parse_ddmmyy(day_s: str, month_s: str, year_s: str) -> date | None:
    """Parse DDMMYY using 2000+YY (matches harvester.utils)."""
    try:
        year = 2000 + int(year_s)
        return date(year, int(month_s), int(day_s))
    except ValueError:
        return None


_BULLETIN_HEADING_RE = re.compile(
    r"(?i)\b(?:parish\s+)?(?:bulletin|newsletter|parish\s+news)\b"
    r"|\bweek\s+beginning\b"
)
# Adjacent masthead date only (Raphoe Drive: "Sunday 19 July 2026" then
# "RAPHOE PARISH NEWSLETTER" on the next line). Long body/memorial lines
# stay out even when they sit next to the heading.
_ADJACENT_DATE_LINE_OFFSETS = (-1, 1, -2, 2)
_MAX_ADJACENT_DATE_LINE_CHARS = 80
_MAX_ADJACENT_DATE_LINE_WORDS = 12
_ADJACENT_BODY_PARAGRAPH_RE = re.compile(
    r"(?i)\b(?:died|death|anniversary|anniversaries|in memory|deceased|"
    r"will take|recently)\b"
)


def _nonempty_text_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _parse_short_adjacent_date_line(line: str) -> date | None:
    """Parse a short date/liturgical neighbour; skip long body paragraphs."""
    if len(line) > _MAX_ADJACENT_DATE_LINE_CHARS:
        return None
    if len(line.split()) > _MAX_ADJACENT_DATE_LINE_WORDS:
        return None
    if _ADJACENT_BODY_PARAGRAPH_RE.search(line):
        return None
    return extract_date_from_string(line)


# Referee Brain slice 1 (stale harder, 29/09/2026): a masthead line that names
# the Sunday liturgically ("16TH SUNDAY OF ORDINARY TIME", "3rd Sunday of
# Advent") is a bulletin heading even when the word bulletin/newsletter is
# missing. Aughavas & Cloone NL1773.pdf ("19th July 2026 16TH SUNDAY OF
# ORDINARY TIME") reached the 27/09/2026 mega as "ok" because only the
# bulletin/newsletter word was accepted. Memorial lines ("died on 9th July
# 2023") carry no liturgical marker, so they still stay None.
_LITURGICAL_MASTHEAD_RE = re.compile(
    r"(?i)\b(?:\d{1,2}(?:st|nd|rd|th)?\s+sunday\s+(?:of|in)\b"
    r"|sunday\s+of\s+(?:advent|lent|easter|the\s+year)"
    r"|ordinary\s+time|palm\s+sunday|pentecost\s+sunday|trinity\s+sunday"
    r"|corpus\s+christi|christ\s+the\s+king|holy\s+family|baptism\s+of\s+the\s+lord)"
)
_FULL_YEAR_RE = re.compile(r"\b20\d{2}\b")


def extract_bulletin_date_from_text(text: str) -> date | None:
    """Parse a date from bulletin/newsletter heading lines in PDF text.

    Same-line heading dates win first (Holy Cross: ``Bulletin 11th & 12th
    July 2026``). If that heading has no date, look at the previous and next
    1–2 non-empty lines only when they are short date/liturgical lines.
    Does not scan the whole page, so a memorial such as ``died on 9th July
    2023`` with no nearby bulletin/newsletter word stays ``None``.

    Second pass: a liturgical masthead line ("16TH SUNDAY OF ORDINARY TIME")
    with a full dated (year-bearing) date on the same or an adjacent short
    line also counts. Yearless dates are never promoted here.
    """
    lines = _nonempty_text_lines(text)
    for index, line in enumerate(lines):
        if not _BULLETIN_HEADING_RE.search(line):
            continue
        parsed = extract_date_from_string(line)
        if parsed:
            return parsed
        for offset in _ADJACENT_DATE_LINE_OFFSETS:
            neighbour_index = index + offset
            if 0 <= neighbour_index < len(lines):
                parsed = _parse_short_adjacent_date_line(lines[neighbour_index])
                if parsed:
                    return parsed
    for index, line in enumerate(lines):
        if not _LITURGICAL_MASTHEAD_RE.search(line):
            continue
        if _ADJACENT_BODY_PARAGRAPH_RE.search(line):
            continue
        if _FULL_YEAR_RE.search(line):
            parsed = extract_date_from_string(line)
            if parsed:
                return parsed
        for offset in _ADJACENT_DATE_LINE_OFFSETS:
            neighbour_index = index + offset
            if 0 <= neighbour_index < len(lines):
                neighbour = lines[neighbour_index]
                if not _FULL_YEAR_RE.search(neighbour):
                    continue
                parsed = _parse_short_adjacent_date_line(neighbour)
                if parsed:
                    return parsed
    return None


def verdict_for_extracted_date(extracted: date, target: date) -> FreshnessVerdict:
    """Compare an already-parsed bulletin date with the harvest Sunday."""
    week_start, week_end = week_window(target)
    if week_start <= extracted <= week_end:
        return FreshnessVerdict(
            status="fresh",
            extracted_date=extracted,
            reason="in_bulletin_week",
            days_from_target=(extracted - target).days,
        )

    days_from_target = (extracted - target).days
    if 0 < days_from_target <= MAX_STALE_DAYS_FROM_TARGET:
        return FreshnessVerdict(
            status="fresh",
            extracted_date=extracted,
            reason="within_grace_days",
            days_from_target=days_from_target,
        )

    direction = "ahead" if days_from_target > 0 else "behind"
    return FreshnessVerdict(
        status="stale",
        extracted_date=extracted,
        reason=f"date_{direction}_of_target",
        days_from_target=days_from_target,
    )


def check_bulletin_freshness(url: str, target: date) -> FreshnessVerdict:
    """
    Decide whether *url* points at the current harvest week's bulletin.

    * unknown — no parseable date (do not auto-reject; parish may use undated URLs)
    * fresh   — date in the bulletin week, or up to MAX_STALE_DAYS ahead of target
    * stale   — date before the bulletin week, or more than MAX_STALE_DAYS ahead
    """
    extracted = extract_bulletin_date(url)
    if extracted is None:
        # Yearless "Sunday-9th-August.pdf" / "5th-July.pdf" (no calendar
        # year in the filename). Use the harvest Sunday's year so these
        # can still be freshness-checked instead of silently passing as
        # unknown (found 2026-08-18, milfordrathmullanparishes: a pinned
        # July file was reported ok because extract_bulletin_date returned
        # None).
        extracted = yearless_slug_date(url, target.year, near=target)
    if extracted is None:
        return FreshnessVerdict(status="unknown", reason="no_date_in_url")

    # Hashed/UUID page scans (Iskaheen /2026/08/<uuid>-rotated.jpg) have no
    # day-of-month. extract_bulletin_date then uses the 1st of the upload
    # folder, which is 15 days behind a mid-month Sunday and fails the 8-day
    # grace window even when the parish posted this month's bulletin.
    basename = unquote(url or "").rsplit("/", 1)[-1]
    if (
        extracted.day == 1
        and extracted.year == target.year
        and extracted.month == target.month
        and (
            _opaque_hash_spans(basename)
            or _PAGE_SCAN_BASENAME_RE.match(basename)
        )
    ):
        return FreshnessVerdict(
            status="fresh",
            extracted_date=target,
            reason="upload_folder_matches_target_month",
            days_from_target=0,
        )

    return verdict_for_extracted_date(extracted, target)


def suggest_retry_strategy(
    result: FetchResult,
    entry: ParishEntry | None = None,
) -> str:
    """
    Return a machine-readable hint for the next harvest attempt.

    Strategies (in order of preference for operators):
      rescrape_bulletin_page — re-scan listing page for fresher links
      try_date_patterns      — URL prediction / pattern detect (A–H parishes)
      retrain_recipe         — extension recipe when replay was used
      manual_review          — undated URL or no bulletin page
    """
    url = (result.url or "").lower()
    pattern = (entry.pattern if entry else "") or ""
    has_bulletin_page = bool(entry and (entry.bulletin_page or "").strip())
    content_type = (entry.content_type if entry else "") or ""

    if "recipe" in (result.file_type or "") or pattern in {"learned", "recipe"}:
        return "retrain_recipe"
    if has_bulletin_page and content_type != "html_link":
        return "rescrape_bulletin_page"
    if pattern and pattern not in {"html_link", "F", "greenlough", "clonleigh"}:
        return "try_date_patterns"
    if not extract_bulletin_date(url):
        return "manual_review"
    return "manual_review"


def mark_result_stale(
    result: FetchResult,
    verdict: FreshnessVerdict,
    *,
    entry: ParishEntry | None = None,
) -> FetchResult:
    """Convert an ok result into a stale rejection with retry metadata."""
    strategy = suggest_retry_strategy(result, entry)
    date_str = verdict.extracted_date.isoformat() if verdict.extracted_date else "unknown"
    result.is_stale = True
    result.stale_reason = verdict.reason
    result.retry_strategy = strategy
    result.status = "error"
    result.error = (
        f"Stale bulletin rejected for mega PDF "
        f"(bulletin date {date_str}, {verdict.reason})"
    )
    result.diagnosis = {
        **(result.diagnosis if isinstance(result.diagnosis, dict) else {}),
        "failure_stage": "stale_rejected",
        "bulletin_date": date_str,
        "stale_reason": verdict.reason,
        "recipe_worked": True,
    }
    if result.file_path and result.file_path.exists():
        try:
            result.file_path.unlink()
        except OSError:
            pass
    result.file_path = None
    return result


def _parse_iso_date(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parts = text.split("-")
        if len(parts) != 3:
            return None
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


# Body-year trap for undated /latest/ PDFs whose heading has no week stamp
# (Attymass 08/10/2026: only 2020–2022 years in the text, still marked ok).
_BODY_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# Newest year in the PDF must be at least this many years behind target.
_ANCIENT_BODY_YEAR_GAP = 3


def read_pdf_text_head(path: Path, max_pages: int = 4) -> str:
    """Embedded PDF text from the first pages (same text born-digital OCR sees).

    Uses PyPDF2 — that is what CI installs (requirements.txt). Importing
    ``pypdf`` here failed silently on GitHub Actions, returned empty text,
    and let Ardara/Attymass skip the body stale gate (08/10/2026).
    """
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
    except Exception:
        return ""
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks)


def verdict_from_ancient_body_years(
    text: str, target: date
) -> FreshnessVerdict | None:
    """Stale when the PDF only mentions years far behind the harvest year.

    Does not invent a week stamp from story text. Requires at least two year
    hits and no year in target.year-1 .. future, so a current bulletin that
    mentions an old fundraising year plus 2026 stays unknown/fresh elsewhere.
    """
    years = [int(match) for match in _BODY_YEAR_RE.findall(text or "")]
    if len(years) < 2:
        return None
    newest = max(years)
    if newest >= target.year - 1:
        return None
    if newest > target.year - _ANCIENT_BODY_YEAR_GAP:
        return None
    extracted = date(newest, 12, 31)
    return FreshnessVerdict(
        status="stale",
        extracted_date=extracted,
        reason="body_years_only_ancient",
        days_from_target=(extracted - target).days,
    )


def pdf_body_stale_verdict(path: Path, target: date) -> FreshnessVerdict | None:
    """Return stale when PDF heading or ancient-only years prove the file is old.

    Harvest-time referee uses embedded PDF text here — the same characters a
    later OCR pass would read on born-digital pages. Vision OCR still runs
    after the mega for image-only scans; those stay unknown until a heading
    date appears.
    """
    text = read_pdf_text_head(path)
    if not text.strip():
        return None
    body_date = extract_bulletin_date_from_text(text)
    if body_date is not None:
        verdict = verdict_for_extracted_date(body_date, target)
        if verdict.status == "stale":
            return verdict
        return None
    return verdict_from_ancient_body_years(text, target)


def freshness_verdict_for_ok_result(
    result: FetchResult,
    target: date,
    *,
    report_bulletin_date: date | None = None,
) -> FreshnessVerdict:
    """URL / report date / PDF-body freshness for one ok download.

    Report ``bulletin_date`` or URL date is the first guess, but a provably
    old PDF body (heading date or ancient-only years) always wins — otherwise
    a this-week slug with last month's print slips into the mega (Ardara
    08/10/2026: URL 04/10, body 13/09).
    """
    url = (result.url or "").strip()
    pdf_path = result.file_path
    candidates: list[Path] = []
    if pdf_path is not None:
        candidates.append(Path(pdf_path))
    # Harvest may have already promoted to Bulletins/<key>.pdf / current/.
    key = str(getattr(result, "key", "") or "").strip()
    if key:
        root = Path(__file__).resolve().parent.parent
        candidates.append(root / "Bulletins" / f"{key}.pdf")
        candidates.append(root / "Bulletins" / "current" / f"{key}.pdf")

    if report_bulletin_date is not None:
        verdict = verdict_for_extracted_date(report_bulletin_date, target)
    elif url:
        verdict = check_bulletin_freshness(url, target)
    else:
        verdict = FreshnessVerdict(status="unknown", reason="no_date_in_url")

    # Any on-disk PDF that proves stale wins (do not stop at the first path
    # that exists but has no extractable heading — Ardara 08/10/2026).
    for path in candidates:
        if not path.exists():
            continue
        body_stale = pdf_body_stale_verdict(path, target)
        if body_stale is not None:
            return body_stale
    return verdict


def reclassify_stale_downloaded_in_report(
    report: dict,
    target: date,
    *,
    current_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Move stale ``downloaded`` rows to ``stale_rejected``; delete their PDFs.

    Catches rows that kept a dated URL / ``bulletin_date`` as ok (e.g. Cork
    20/09 still in downloaded for week 04/10) before the mega stitch stubs
    every file on disk as ok.
    """
    from .report import _recompute_summary, _remove_parish_from_sections
    from .utils import format_uk_date

    downloaded = [
        item
        for item in (report.get("downloaded") or [])
        if isinstance(item, dict) and item.get("parish")
    ]
    rejected: list[dict[str, object]] = []
    kept: list[dict] = []
    stale_dir = (current_dir.parent / "stale") if current_dir else None
    if stale_dir is not None:
        stale_dir.mkdir(parents=True, exist_ok=True)

    for item in downloaded:
        key = str(item.get("parish") or "").strip()
        url = str(item.get("url") or "").strip()
        report_date = _parse_iso_date(item.get("bulletin_date"))
        pdf_path: Path | None = None
        if current_dir is not None:
            file_name = str(item.get("file") or f"{key}.pdf").strip() or f"{key}.pdf"
            for candidate in (
                current_dir / file_name,
                current_dir / f"{key}.pdf",
                current_dir.parent / f"{key}.pdf",
            ):
                if candidate.exists():
                    pdf_path = candidate
                    break


        from .fetcher import FetchResult

        stub = FetchResult(
            key=key,
            display_name=str(item.get("display_name") or key),
            status="ok",
            url=url,
            file_path=pdf_path,
            file_type=str(item.get("file_type") or "pdf"),
        )
        verdict = freshness_verdict_for_ok_result(
            stub, target, report_bulletin_date=report_date
        )
        if verdict.status != "stale":
            kept.append(item)
            continue

        date_str = (
            verdict.extracted_date.isoformat() if verdict.extracted_date else "unknown"
        )
        error = (
            f"Stale bulletin rejected for mega PDF "
            f"(bulletin date {date_str}, {verdict.reason})"
        )
        kept_name = None
        if pdf_path is not None and pdf_path.exists() and stale_dir is not None:
            dest = stale_dir / pdf_path.name
            try:
                pdf_path.replace(dest)
                kept_name = dest.name
            except OSError:
                try:
                    pdf_path.unlink()
                except OSError:
                    pass
        elif pdf_path is not None and pdf_path.exists():
            try:
                pdf_path.unlink()
            except OSError:
                pass

        stale_row = {
            "parish": key,
            "display_name": stub.display_name,
            "url": url,
            "reason": verdict.reason,
            "retry_strategy": suggest_retry_strategy(stub),
            "error": error,
            "bulletin_date": date_str if date_str != "unknown" else None,
            "bulletin_date_uk": (
                format_uk_date(date_str) if date_str != "unknown" else None
            ),
        }
        if kept_name:
            stale_row["file"] = kept_name
        _remove_parish_from_sections(report, key)
        if not isinstance(report.get("stale_rejected"), list):
            report["stale_rejected"] = []
        report["stale_rejected"].append(
            {k: v for k, v in stale_row.items() if v is not None}
        )
        rejected.append(
            {
                "key": key,
                "display_name": stub.display_name,
                "url": url,
                "extracted_date": date_str if date_str != "unknown" else None,
                "reason": verdict.reason,
                "retry_strategy": stale_row["retry_strategy"],
            }
        )

    report["downloaded"] = kept
    _recompute_summary(report)
    return rejected


def build_mega_stitch_results(
    report: dict,
    current_dir: Path,
    target: date,
) -> list[FetchResult]:
    """Build mega stitch inputs from report ``downloaded`` only (not every PDF).

    Orphan PDFs left on disk from older weeks never become empty-URL ok stubs.
    Re-runs the safety net and syncs any new stale rejects back into *report*.
    """
    from .fetcher import FetchResult
    from .report import _recompute_summary, _remove_parish_from_sections
    from .utils import format_uk_date

    results: list[FetchResult] = []
    by_key: dict[str, dict] = {}
    for item in report.get("downloaded") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("parish") or "").strip()
        if not key:
            continue
        by_key[key] = item
        file_name = str(item.get("file") or f"{key}.pdf").strip() or f"{key}.pdf"
        pdf_path = current_dir / file_name
        if not pdf_path.exists():
            pdf_path = current_dir / f"{key}.pdf"
        if not pdf_path.exists():
            continue
        results.append(
            FetchResult(
                key=key,
                display_name=str(item.get("display_name") or key),
                status="ok",
                url=str(item.get("url") or ""),
                file_path=pdf_path,
                file_type=str(item.get("file_type") or "pdf"),
            )
        )
    apply_freshness_safety_net(results, target)

    ok: list[FetchResult] = []
    for result in results:
        if result.status == "ok" and not result.is_stale:
            ok.append(result)
            continue
        # Safety net rejected (e.g. undated URL + old PDF heading) — sync report.
        item = by_key.get(result.key) or {}
        date_str = None
        if isinstance(result.diagnosis, dict):
            date_str = result.diagnosis.get("bulletin_date")
        stale_row = {
            "parish": result.key,
            "display_name": result.display_name,
            "url": result.url or item.get("url") or "",
            "reason": result.stale_reason or "date_behind_of_target",
            "retry_strategy": result.retry_strategy or "manual_review",
            "error": result.error
            or "Stale bulletin rejected for mega PDF",
        }
        if date_str and date_str != "unknown":
            stale_row["bulletin_date"] = date_str
            stale_row["bulletin_date_uk"] = format_uk_date(str(date_str))
        _remove_parish_from_sections(report, result.key)
        if not isinstance(report.get("stale_rejected"), list):
            report["stale_rejected"] = []
        report["stale_rejected"].append(stale_row)

    _recompute_summary(report)
    return ok


def apply_freshness_safety_net(
    results: list[FetchResult],
    target: date,
    *,
    entries_by_key: dict[str, ParishEntry] | None = None,
    retry_queue_path: Path | None = None,
) -> dict[str, object]:
    """
    Second-pass gate before mega PDF stitch.

    Catches stale ok results that slipped past in-fetch recovery (e.g. undated
    URL that was actually old, empty-URL stitch stubs rebuilt from disk, or
    results rebuilt from cache).

    Uses ``freshness_verdict_for_ok_result`` so a this-week URL or report date
    cannot keep a PDF whose body heading (or ancient-only years) is stale.
    A this-week body heading does not invent ``fresh`` over an unknown URL.
    """
    entries_by_key = entries_by_key or {}
    queue_path = retry_queue_path or _RETRY_QUEUE_PATH
    rejected: list[dict[str, object]] = []
    retry_items: list[dict[str, object]] = []

    for result in results:
        if result.is_stale:
            continue
        if result.status != "ok":
            continue
        has_pdf = result.file_path is not None and Path(result.file_path).exists()
        if not (result.url or "").strip() and not has_pdf:
            continue

        verdict = freshness_verdict_for_ok_result(result, target)
        if verdict.status != "stale":
            continue

        entry = entries_by_key.get(result.key)
        mark_result_stale(result, verdict, entry=entry)
        rejected.append(
            {
                "key": result.key,
                "display_name": result.display_name,
                "url": result.url,
                "extracted_date": (
                    verdict.extracted_date.isoformat() if verdict.extracted_date else None
                ),
                "reason": verdict.reason,
                "retry_strategy": result.retry_strategy,
            }
        )
        retry_items.append(
            {
                "key": result.key,
                "display_name": result.display_name,
                "strategy": result.retry_strategy,
                "url": result.url,
                "bulletin_page": (entry.bulletin_page if entry else "") or "",
                "pattern": (entry.pattern if entry else "") or "",
                "message": (
                    f"Stale bulletin ({verdict.extracted_date}) — "
                    f"try {result.retry_strategy}"
                ),
            }
        )

    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds"),
        "harvest_target": target.isoformat(),
        "rejected_from_mega": rejected,
        "retry": retry_items,
    }
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload
