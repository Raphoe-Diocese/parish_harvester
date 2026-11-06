"""Score a bulletin reading against phrases taken from the printed page.

This does not call vision and it does not invent text. A pass means every
required phrase is present and every banned smash token is absent.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NAME_ONLY = "matched by parish name only"


@dataclass(frozen=True)
class ReadingScore:
    ok: bool
    missing: list[str]
    banned_hits: list[str]
    name_only: bool


def fold_reading(text: str) -> str:
    """Lower-case, strip accents, keep letters and digits."""
    raw = unicodedata.normalize("NFKD", text or "")
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower().replace("-", " ")
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _contains(hay_folded: str, hay_digits: str, phrase: str) -> bool:
    needle = fold_reading(phrase)
    if needle and needle in hay_folded:
        return True
    digits = re.sub(r"\D", "", phrase)
    return len(digits) >= 7 and digits in hay_digits


# Phrases read off the printed page on 31/10/2026. Not copied from OCR HTML.
ANNAGRY_MUST = [
    "30th Sunday of Ordinary Time",
    "074-9548902",
    "Teach Pobail Mhuire",
    "Realt na Mara Anagaire",
    "Aifrinn na Seachtaine",
    "Jimmy Boyle",
    "Missa Pro Populo",
    "Cuimhneachain bais",
    "Mile buiochas",
]
ANNAGRY_BANNED = ["aodui", "Gallachsir"]

GORT_MUST = [
    "Aifrinn na Seachtaine",
    "Deireadh Fomhair",
    "Antoin Og Penrose",
    "John J Sweeney",
    "Togadh",
    "Brid O Donnell",
]

NEWTOWN_MUST = [
    "Baithin",
    "Edmund Curran",
    "Mary McIvor",
    "All Saints Day",
    "Pro-Populo",
]


def score_reading(
    text: str,
    must_have: list[str],
    must_not: list[str] | None = None,
) -> ReadingScore:
    """Return whether *text* is a clean reading of the required phrases."""
    folded = fold_reading(text)
    digits = re.sub(r"\D", "", text or "")
    missing = [phrase for phrase in must_have if not _contains(folded, digits, phrase)]
    banned_hits = [
        phrase for phrase in (must_not or []) if fold_reading(phrase) in folded
    ]
    name_only = _NAME_ONLY in folded
    if name_only:
        banned_hits = banned_hits + [_NAME_ONLY]
    return ReadingScore(
        ok=not missing and not banned_hits and not name_only,
        missing=missing,
        banned_hits=banned_hits,
        name_only=name_only,
    )
