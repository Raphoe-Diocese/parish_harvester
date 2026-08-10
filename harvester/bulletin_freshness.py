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
)

if TYPE_CHECKING:
    from .fetcher import FetchResult, ParishEntry

# Match harvest_log / extension: >8 calendar days from harvest target = stale.
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
# and only "passed" by accident, via the 8-day grace window, rather than the
# correct in_bulletin_week match (found 2026-08-10 while auditing every
# grace-window "ok" for hidden freshness bugs).
_LEADING_ORDINAL_RE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)[\s_-]*(?:sun|suday|sunday|ordinary|advent|lent|easter|christmas)",
    re.I,
)


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
            ordinal_match = _LEADING_ORDINAL_RE.match(basename)
            slug_day = re.search(r"(?<!\d)(0?[1-9]|[12]\d|3[01])(?!\d)", basename)
            if slug_day and not (
                ordinal_match and slug_day.start(1) == ordinal_match.start(1)
            ):
                return _safe_date(folder_year, folder_month, int(slug_day.group(1)))
            return _safe_date(folder_year, folder_month, 1)
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


def check_bulletin_freshness(url: str, target: date) -> FreshnessVerdict:
    """
    Decide whether *url* points at the current harvest week's bulletin.

    * unknown — no parseable date (do not auto-reject; parish may use undated URLs)
    * fresh   — date within the bulletin week or within MAX_STALE_DAYS of target
    * stale   — explicit date clearly outside the acceptable window
    """
    extracted = extract_bulletin_date(url)
    if extracted is None:
        return FreshnessVerdict(status="unknown", reason="no_date_in_url")

    week_start, week_end = week_window(target)
    if week_start <= extracted <= week_end:
        return FreshnessVerdict(
            status="fresh",
            extracted_date=extracted,
            reason="in_bulletin_week",
            days_from_target=(extracted - target).days,
        )

    days_from_target = (extracted - target).days
    days_old = abs(days_from_target)
    if days_old <= MAX_STALE_DAYS_FROM_TARGET:
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
    URL that was actually old, or results rebuilt from cache).
    """
    entries_by_key = entries_by_key or {}
    queue_path = retry_queue_path or _RETRY_QUEUE_PATH
    rejected: list[dict[str, object]] = []
    retry_items: list[dict[str, object]] = []

    for result in results:
        if result.is_stale:
            continue
        if result.status != "ok" or not result.url:
            continue

        verdict = check_bulletin_freshness(result.url, target)
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
