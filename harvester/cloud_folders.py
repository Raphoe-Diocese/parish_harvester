"""
cloud_folders.py — Google Drive / OneDrive folder listings with dated PDF rows.

Filenames like ``26.06.14.pdf`` use YY.MM.DD (year 2000+YY, so 27.06.14 → 2027-06-14).
"""
from __future__ import annotations

import re
from datetime import date

_YY_MM_DD_RE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{2})(?!\d)")
_YY_MM_DD_FILE_RE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{2})(?:\.pdf)?(?!\d)", re.IGNORECASE)

CLOUD_DATE_FORMAT_YY_MM_DD = "YY.MM.DD"


def detect_cloud_date_format(text: str) -> str | None:
    """Return format id when *text* looks like a YY.MM.DD bulletin filename."""
    if _YY_MM_DD_FILE_RE.search(text or ""):
        return CLOUD_DATE_FORMAT_YY_MM_DD
    return None


def parse_yy_mm_dd(text: str) -> date | None:
    """Parse ``YY.MM.DD`` from filename or label (2000+YY for all future years)."""
    match = _YY_MM_DD_RE.search(text or "")
    if not match:
        return None
    yy = int(match.group(1))
    mm = int(match.group(2))
    dd = int(match.group(3))
    try:
        return date(2000 + yy, mm, dd)
    except ValueError:
        return None


def format_cloud_folder_label(target: date, fmt: str = CLOUD_DATE_FORMAT_YY_MM_DD, *, with_pdf: bool = True) -> str:
    """Build the visible row label for *target* (e.g. ``27.06.14.pdf`` for 2027-06-14)."""
    if fmt != CLOUD_DATE_FORMAT_YY_MM_DD:
        raise ValueError(f"Unsupported cloud folder date format: {fmt}")
    bare = f"{target.year % 100:02d}.{target.month:02d}.{target.day:02d}"
    return f"{bare}.pdf" if with_pdf else bare


def cloud_folder_date_tokens(target: date) -> list[str]:
    """Tokens to match this Sunday's row in folder listings."""
    label_pdf = format_cloud_folder_label(target, with_pdf=True)
    label_bare = format_cloud_folder_label(target, with_pdf=False)
    return [label_pdf, label_bare, label_pdf.lower(), label_bare.lower()]


def is_cloud_folder_url(url: str) -> bool:
    """True when URL is a shared cloud folder (not a single file)."""
    lower = (url or "").lower()
    if "drive.google.com" in lower and "/folders/" in lower:
        return True
    if "onedrive.live.com" in lower and ("?id=" in lower or "/redir" in lower):
        return True
    if "sharepoint.com" in lower and any(
        marker in lower for marker in ("/documents", "/shared", "folder", "/forms/allitems.aspx")
    ):
        return True
    if "1drv.ms" in lower:
        return True
    return False


def is_cloud_file_url(url: str) -> bool:
    """True when URL is a single cloud file preview (after clicking a folder row)."""
    lower = (url or "").lower()
    if "drive.google.com/file/d/" in lower:
        return True
    if "onedrive.live.com" in lower and "download" in lower:
        return True
    return False


def cloud_folder_selector_candidates(target: date, fmt: str = CLOUD_DATE_FORMAT_YY_MM_DD) -> list[str]:
    """Playwright selectors for the dated bulletin row."""
    label_pdf = format_cloud_folder_label(target, fmt, with_pdf=True)
    label_bare = format_cloud_folder_label(target, fmt, with_pdf=False)
    escaped_pdf = label_pdf.replace("'", "\\'")
    escaped_bare = label_bare.replace("'", "\\'")
    return [
        f'[role="row"]:has-text("{escaped_pdf}")',
        f'[role="gridcell"]:has-text("{escaped_pdf}")',
        f'[role="row"]:has-text("{escaped_bare}")',
        f':has-text("{escaped_pdf}")',
        f':has-text("{escaped_bare}")',
    ]


def is_cloud_folder_click_step(step: dict) -> bool:
    """True when a click step should rewrite its date each harvest."""
    if not isinstance(step, dict) or step.get("action") != "click":
        return False
    if step.get("cloud_folder") or step.get("date_format"):
        return True
    blob = " ".join(
        str(step.get(k) or "")
        for k in ("text", "selector", "href")
    )
    return detect_cloud_date_format(blob) is not None


def rewrite_cloud_folder_click_step(step: dict, target: date) -> dict:
    """Rewrite click step to target Sunday's YY.MM.DD row (2026, 2027, 2028, …)."""
    if not is_cloud_folder_click_step(step):
        return step
    fmt = step.get("date_format") or detect_cloud_date_format(
        str(step.get("text") or step.get("selector") or "")
    )
    if not fmt:
        return step
    label_pdf = format_cloud_folder_label(target, fmt, with_pdf=True)
    label_bare = format_cloud_folder_label(target, fmt, with_pdf=False)
    rewritten = dict(step)
    rewritten["text"] = label_pdf
    rewritten["date_format"] = fmt
    rewritten["cloud_folder"] = True
    rewritten["selector"] = f':has-text("{label_bare}")'
    fallbacks = cloud_folder_selector_candidates(target, fmt)
    existing = [
        s.strip()
        for s in (step.get("fallback_selectors") or [])
        if isinstance(s, str) and s.strip()
    ]
    merged: list[str] = []
    for sel in [*fallbacks, *existing]:
        if sel not in merged:
            merged.append(sel)
    rewritten["fallback_selectors"] = merged
    return rewritten


def recipe_uses_cloud_folder(steps: list) -> bool:
    """True when recipe navigates a dated cloud folder listing."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        if is_cloud_folder_click_step(step):
            return True
        url = str(step.get("url") or "")
        if step.get("action") == "goto" and is_cloud_folder_url(url):
            return True
    return False
