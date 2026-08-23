"""Derive official parish display names from parish website URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_NON_PARISH_HOST_SUFFIXES = (
    "facebook.com",
    "google.com",
    "usercontent.google.com",
    "mcn.live",
    "parishpress.net",
    "filesafe.space",
    "raw.githubusercontent.com",
    "wixlabs-pdf-dev.appspot.com",
)

# Slug (hostname first label) -> official display name when auto-parse is wrong.
_SLUG_OVERRIDES: dict[str, str] = {
    "naomhfionan": "Falcarragh",
    "steunanscathedral": "Cathedral",
    "gort-a-choirce": "Gortahork",
    "milfordrathmullanparishes": "Milford Kilkeel",
    "newtownkilleaparish": "Newtown Killea",
    "stranorlarparish": "Stranolar",
    "tawnawillyparish": "Tawnawilly",
    "inverparish": "Inver",
    "annagryparish": "Annagry",
    "templecroneparish": "Templecrone",
    "glenfin-parish": "Glenfin",
    "kilbarron": "Kilbarron",
    "kincasslagh": "Kincasslagh",
    "ardara": "Ardara",
    "carrigart": "Mevagh",
    "drive-1kna8f6t54": "Gartan/Termon (Kilmacrenan)",
    "drive-14alaxt4mv": "Glenties",
    "drive-1m6sogz3de": "Irish Martyrs",
    "drive-1jmslbrliw": "Raphoe",
    "drive-1hh7w-ew0v": "Templecrone",
    "drive-1rjeey-ayy": "Bruckless",
    "holy-cross-church": "Dunfanaghy",
    "ballintra": "Drumholm (Ballintra)",
    "kilmacrenan": "Gartan/Termon (Kilmacrenan)",
    "rathmullan": "Rathmullan",
    "drumholm-parish": "Drumholm (Ballintra)",
}


def _host_slug(url: str) -> str:
    parsed = urlparse(url.strip())
    host = re.sub(r"^www\d*\.", "", (parsed.netloc or "").lower())
    if re.search(r"\bi\d+\.wp\.com\b", host):
        parts = parsed.path.strip("/").split("/")
        if parts:
            host = parts[0].lower()
    return host.split(".")[0] if host else ""


def _title_words(text: str) -> str:
    words = text.replace("-", " ").replace("_", " ").split()
    out: list[str] = []
    for i, word in enumerate(words):
        low = word.lower()
        if i > 0 and low in {"of", "and", "the"}:
            out.append(low)
        elif word:
            out.append(word[0].upper() + word[1:])
    return " ".join(out)


def official_display_name_from_url(url: str) -> str | None:
    """Return a parish display name from its website URL, or None if not a parish site."""
    if not url or not str(url).strip().startswith("http"):
        return None
    parsed = urlparse(url.strip())
    host = re.sub(r"^www\d*\.", "", (parsed.netloc or "").lower())
    if not host:
        return None
    if any(host == suffix or host.endswith("." + suffix) for suffix in _NON_PARISH_HOST_SUFFIXES):
        return None
    if "facebook" in host or "google" in host:
        return None

    slug = _host_slug(url)
    if not slug:
        return None
    if slug in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[slug]

    core = slug
    suffix = ""
    if core.lower().startswith("parishof"):
        core = core[8:]
    if core.endswith("parishes"):
        core = core[:-8]
        suffix = " Parishes"
    elif core.endswith("parish"):
        core = core[:-6]
        suffix = " Parish"

    name = _title_words(core)
    if not name:
        return None
    if suffix and not name.lower().endswith(suffix.strip().lower()):
        name = name + suffix
    return name.strip() or None
