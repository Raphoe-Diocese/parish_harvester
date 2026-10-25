"""Check, after the downloads and before the book, that this Sunday was not missed.

The referee was right to refuse an old file. The miss was saving last week's
file when this week's file was already on the site. This list is the proved
Raphoe misses for 25/10/2026. The date and filename fixes live in utils.py.
If a result is still the old file, the book must not be stitched.
"""

from __future__ import annotations

from datetime import date

# Old file the Sunday harvest kept, and the file that is actually this Sunday.
RAPHOE_REPLACEMENTS = {
    "annagryparish": {
        "old": "181026.pdf",
        "current": "251025.pdf",
    },
    "tawnawillyparish": {
        "old": "Sunday-18th-Oct-26.pdf",
        "current": "Sunday-25th-Oct.-26.pdf",
    },
}

# Same URL every week. The file on the server was updated 23/10/2026.
# A harvest that does not download it again keeps the old text.
RAPHOE_REDOWNLOAD = ("newtownkilleaparish", "drive-1m6sogz3de")


def raphoe_still_on_last_week(key: str, url: str) -> str | None:
    """Return the old filename when this result is last week's file."""
    row = RAPHOE_REPLACEMENTS.get(key)
    if not row:
        return None
    text = url or ""
    if row["old"] in text and row["current"] not in text:
        return row["old"]
    return None


def book_is_blocked(results: list, target: date) -> list[str]:
    """Stop the book only when it would stitch last week's file.

    Newtown Killea and Irish Martyrs use one address every week. They are
    listed by redownload_warnings and do not, on their own, stop the book.
    """
    del target
    blocked: list[str] = []
    for result in results:
        key = str(getattr(result, "key", "") or "")
        url = str(getattr(result, "url", "") or "")
        old = raphoe_still_on_last_week(key, url)
        if old:
            blocked.append(
                f"{key} is still {old}. This Sunday's file is "
                f"{RAPHOE_REPLACEMENTS[key]['current']}."
            )
    return blocked


def redownload_warnings(results: list) -> list[str]:
    """Permanent addresses whose file was updated on 23/10/2026."""
    lines: list[str] = []
    for result in results:
        key = str(getattr(result, "key", "") or "")
        if key in RAPHOE_REDOWNLOAD and getattr(result, "is_stale", False):
            lines.append(
                f"{key} was still marked old. The file on the server was "
                "updated on 23/10/2026. Download it again before trusting the book."
            )
    return lines
