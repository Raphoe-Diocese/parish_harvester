from __future__ import annotations

"""Split diocese mega-bulletin OCR text into per-parish chunks."""

import re
from typing import Iterable


def _name_patterns(display_name: str) -> tuple[list[str], list[str]]:
    """Return (strong_patterns, weak_patterns) for a parish display name.

    Strong patterns may stand alone as title lines (e.g. ``X Parish``,
    ``Parish of X``). Weak patterns are short bare names that only count when
    the next line is a newsletter URL (stitcher banner).
    """
    name = (display_name or "").strip()
    if not name:
        return [], []
    strong: list[str] = []
    weak: list[str] = []
    if name.lower().endswith(" parish"):
        strong.append(name)
        short = name[:-7].strip()
        if short:
            weak.append(short)
    else:
        strong.append(f"{name} Parish")
        # Long bare titles can stand alone; short ones need a URL banner line.
        if len(name) >= 8:
            strong.append(name)
        else:
            weak.append(name)
    short = re.sub(r"\s*\(.*\)\s*", "", name).strip()
    if short and short.lower() != name.lower():
        if short.lower().endswith(" parish") or len(short) >= 8:
            strong.append(short)
        else:
            weak.append(short)
            strong.append(f"{short} Parish")
    strong = sorted({p for p in strong if len(p) >= 3}, key=len, reverse=True)
    weak = sorted(
        {p for p in weak if len(p) >= 3 and p.lower() not in {s.lower() for s in strong}},
        key=len,
        reverse=True,
    )
    return strong, weak


def _cleaned_title(line: str) -> str:
    cleaned = (line or "").strip()
    cleaned = cleaned.rstrip(".,:;!")
    return re.sub(r"\s+", " ", cleaned).strip()


def _line_matches_patterns(cleaned: str, patterns: list[str]) -> bool:
    if not cleaned or len(cleaned) > 80:
        return False
    lower = cleaned.lower()
    for pattern in patterns:
        p = pattern.lower()
        if lower == p:
            return True
        if lower == f"parish of {p}":
            return True
        if lower == f"the parish of {p}":
            return True
    return False


def _line_is_parish_marker(line: str, patterns: list[str]) -> bool:
    """Compatibility helper: true if line matches any of the given patterns."""
    return _line_matches_patterns(_cleaned_title(line), patterns)


def _next_line_is_url(next_line: str) -> bool:
    nxt = (next_line or "").strip().lower()
    return nxt.startswith("http://") or nxt.startswith("https://") or nxt.startswith("www.")


def split_ocr_by_parish(
    ocr_text: str,
    parish_entries: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Map ``parish_key`` → OCR chunk for that parish.

    Finds parish display names as standalone title lines in the mega bulletin
    OCR (including stitcher banners OCR'd as ``Name`` then URL) and slices
    text between consecutive markers.
    """
    text = (ocr_text or "").strip()
    entries = list(parish_entries)
    if not text:
        return {key: "" for key, _ in entries}

    pattern_map: dict[str, tuple[list[str], list[str]]] = {
        key: _name_patterns(display_name) for key, display_name in entries
    }

    markers: list[tuple[int, str]] = []
    lines = text.splitlines(keepends=True)
    # Precompute next non-empty stripped line for each index
    stripped_lines = [ln.strip() for ln in lines]
    next_nonempty: list[str] = [""] * len(lines)
    upcoming = ""
    for i in range(len(lines) - 1, -1, -1):
        next_nonempty[i] = upcoming
        if stripped_lines[i]:
            upcoming = stripped_lines[i]

    offset = 0
    for i, line in enumerate(lines):
        raw_stripped = line.strip()
        cleaned = _cleaned_title(line)
        # "Rathmullan: 087…" body lines — colon titles only count with a URL next.
        if raw_stripped.endswith(":") and not _next_line_is_url(next_nonempty[i]):
            offset += len(line)
            continue
        if cleaned:
            for key, (strong, weak) in pattern_map.items():
                if _line_matches_patterns(cleaned, strong):
                    markers.append((offset, key))
                    break
                if _line_matches_patterns(cleaned, weak) and _next_line_is_url(next_nonempty[i]):
                    markers.append((offset, key))
                    break
        offset += len(line)

    if not markers:
        return {key: "" for key, _ in entries}

    earliest: dict[str, int] = {}
    for pos, key in markers:
        if key not in earliest or pos < earliest[key]:
            earliest[key] = pos

    ordered = sorted(earliest.items(), key=lambda item: item[1])
    chunks: dict[str, str] = {key: "" for key, _ in entries}

    for idx, (key, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(text)
        chunks[key] = text[start:end].strip()

    return chunks
