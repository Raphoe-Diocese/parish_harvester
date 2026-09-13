"""Known same-parish recipe aliases. Do not invent extras.

Frank (23/08/2026): Ballintra is Drumholm. Kilmacrenan is the same
Google Drive file as Gartan/Termon (id ``1KnA8F6t54…`` / recipe
``drive-1kna8f6t54``). Only those two aliases are recorded here.
"""

from __future__ import annotations

import re

# alias recipe key -> canonical recipe key (the one that has the PDF)
ALIAS_TO_CANONICAL: dict[str, str] = {
    "ballintra": "drumholm-parish",
    "kilmacrenan": "drive-1kna8f6t54",
}

# Harvest / workflow input names that are not skip-aliases. Bruckless is the
# real recipe ``drive-1rjeey-ayy`` — Frank should not have to type the Drive id.
HARVEST_INPUT_ALIASES: dict[str, str] = {
    "bruckless": "drive-1rjeey-ayy",
}

# One A–Z name for the canonical parish (includes the alias in brackets).
COMBINED_DISPLAY_NAMES: dict[str, str] = {
    "drumholm-parish": "Drumholm (Ballintra)",
    "drive-1kna8f6t54": "Gartan/Termon (Kilmacrenan)",
}

# Display-name spellings that must collapse to the same grid / jump row.
_NAME_TO_CANONICAL: dict[str, str] = {
    "ballintra": "drumholm-parish",
    "ballintra parish": "drumholm-parish",
    "drumholm": "drumholm-parish",
    "drumholm (ballintra)": "drumholm-parish",
    "kilmacrenan": "drive-1kna8f6t54",
    "gartan/termon": "drive-1kna8f6t54",
    "gartan / termon": "drive-1kna8f6t54",
    "gartan/termon (kilmacrenan)": "drive-1kna8f6t54",
}
_NAME_TO_CANONICAL_NORM: dict[str, str] = {
    re.sub(r"[^a-z0-9]+", "", key): value for key, value in _NAME_TO_CANONICAL.items()
}

_FACEBOOK_HOST = "facebook.com"
_NORM_RE = re.compile(r"[^a-z0-9]+")


DRIVE_FOLDER_LISTING_ERROR = "Drive folder listing, not a file"


def resolve_harvest_key(value: str) -> str:
    """Map a harvest input (``bruckless``) to the recipe key."""
    key = (value or "").strip().lower()
    if not key:
        return ""
    return HARVEST_INPUT_ALIASES.get(key, key)


def is_drive_folder_listing(url: str) -> bool:
    lower = (url or "").lower()
    return "drive.google.com" in lower and "/folders/" in lower


def reject_drive_folder_listing(result: object) -> object:
    """If an ok result still points at a Drive folder, mark it failed."""
    status = getattr(result, "status", "")
    url = getattr(result, "url", "") or ""
    if status == "ok" and is_drive_folder_listing(url):
        result.status = "error"
        result.error = DRIVE_FOLDER_LISTING_ERROR
    return result


def canonical_key(parish_key: str) -> str:
    key = (parish_key or "").strip()
    return ALIAS_TO_CANONICAL.get(key, key)


def is_alias_key(parish_key: str) -> bool:
    return (parish_key or "").strip() in ALIAS_TO_CANONICAL


def combined_display_name(parish_key: str) -> str | None:
    """Combined A–Z name for a canonical or alias key, if we have one."""
    key = canonical_key(parish_key)
    return COMBINED_DISPLAY_NAMES.get(key)


def _norm_name(value: str) -> str:
    return _NORM_RE.sub("", (value or "").lower())


def canonical_key_for_name(display_name: str) -> str | None:
    raw = (display_name or "").strip()
    if not raw:
        return None
    direct = _NAME_TO_CANONICAL.get(raw.lower())
    if direct:
        return direct
    return _NAME_TO_CANONICAL_NORM.get(_norm_name(raw))


def name_lookup_keys(display_name: str) -> list[str]:
    """Normalised keys to match a grid name to an internal parish page."""
    keys: list[str] = []
    raw = (display_name or "").strip()
    if not raw:
        return keys
    primary = _norm_name(raw)
    if primary:
        keys.append(primary)
    stripped = re.sub(r"\([^)]*\)", " ", raw).strip()
    extra = _norm_name(stripped)
    if extra and extra not in keys:
        keys.append(extra)
    return keys


def _prefer_bulletin_url(current: str, candidate: str) -> str:
    """Keep the downloadable bulletin URL, not a Facebook page."""
    cur = (current or "").strip()
    cand = (candidate or "").strip()
    if not cand:
        return cur
    if not cur:
        return cand
    cur_fb = _FACEBOOK_HOST in cur.lower()
    cand_fb = _FACEBOOK_HOST in cand.lower()
    if cur_fb and not cand_fb:
        return cand
    if cand_fb and not cur_fb:
        return cur
    if cand.lower().split("?", 1)[0].endswith(".pdf") and not cur.lower().split("?", 1)[0].endswith(".pdf"):
        return cand
    return cur


def collapse_named_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Merge alias rows so Ballintra is not listed beside Drumholm."""
    merged: dict[str, tuple[str, str]] = {}
    passthrough: list[tuple[str, str]] = []
    for name, url in links:
        display = (name or "").strip()
        href = (url or "").strip()
        key = canonical_key_for_name(display)
        if not key:
            passthrough.append((display, href))
            continue
        label = COMBINED_DISPLAY_NAMES.get(key) or display
        prev = merged.get(key)
        if prev is None:
            merged[key] = (label, href)
        else:
            merged[key] = (label, _prefer_bulletin_url(prev[1], href))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, url in list(merged.values()) + passthrough:
        token = _norm_name(name)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append((name, url))
    out.sort(key=lambda pair: pair[0].lower())
    return out
