from __future__ import annotations

"""Split diocese mega-bulletin OCR text into per-parish chunks."""

import re
from typing import Iterable


def _name_patterns(display_name: str) -> list[str]:
    """Build search patterns for a parish display name."""
    name = (display_name or "").strip()
    if not name:
        return []
    patterns = [name]
    if name.lower().endswith(" parish"):
        patterns.append(name[:-7].strip())
    # Strip parenthetical amalgamation labels: "Ballinascreen (& Desertmartin ...)"
    short = re.sub(r"\s*\(.*\)\s*", "", name).strip()
    if short and short not in patterns:
        patterns.append(short)
    return [p for p in patterns if len(p) >= 3]


def split_ocr_by_parish(
    ocr_text: str,
    parish_entries: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Map ``parish_key`` → OCR chunk for that parish.

    Finds parish display names as standalone lines in the mega bulletin OCR
    text and slices text between consecutive markers.

    Parameters
    ----------
    ocr_text:
        Full diocese bulletin plain text.
    parish_entries:
        ``(parish_key, display_name)`` pairs.

    Returns
    -------
    dict[str, str]
        Chunk per parish key; missing parishes get ``""``.
    """
    text = (ocr_text or "").strip()
    if not text:
        return {key: "" for key, _ in parish_entries}

    markers: list[tuple[int, str]] = []

    for parish_key, display_name in parish_entries:
        for pattern in _name_patterns(display_name):
            escaped = re.escape(pattern)
            for match in re.finditer(rf"(?m)^\s*{escaped}\s*$", text, flags=re.IGNORECASE):
                markers.append((match.start(), parish_key))

    if not markers:
        return {key: "" for key, _ in parish_entries}

    # Keep earliest occurrence per parish key.
    earliest: dict[str, int] = {}
    for pos, key in markers:
        if key not in earliest or pos < earliest[key]:
            earliest[key] = pos

    ordered = sorted(earliest.items(), key=lambda item: item[1])
    chunks: dict[str, str] = {key: "" for key, _ in parish_entries}

    for idx, (key, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(text)
        chunks[key] = text[start:end].strip()

    return chunks
