"""One reader layout for every parish bulletin.

Runs on the text of every diocese. It does not look up a parish name
and it does not invent words. A printed label becomes its own block.
A phone number ends a line. The next name or sentence starts the next line.
"""

from __future__ import annotations

import re

# One-word labels bulletins print before a colon: Web: Email: Tel:
_ONE_WORD_LABEL = r"Web|E-?mail|Facebook|Instagram|Tel|Telephone|Webpage|Twitter|YouTube"
# Two to six words, each already starting with a capital, then a colon.
_TITLE_LABEL = r"[A-ZÁÉÍÓÚ][\w'’.-]*(?:\s+[A-ZÁÉÍÓÚ][\w'’.-]*){1,5}"
# PARISH NOTICES: and SUNDAY COLLECTION:
_CAPS_LABEL = r"[A-ZÁÉÍÓÚ]{2,}(?:\s+[A-ZÁÉÍÓÚ]{2,}){1,5}"
_LABEL = rf"(?:{_ONE_WORD_LABEL}|{_TITLE_LABEL}|{_CAPS_LABEL})"

_COLON_LABEL = re.compile(rf"\s+(?=(?:{_LABEL})\s*:)")
_BARE_LABEL = re.compile(
    r"\s+(?=(?:Charity\s+No\.|Parish\s+Child\s+Safeguarding(?:\s+Liaisons)?)\b)",
    re.IGNORECASE,
)
_LABEL_LINE = re.compile(rf"^({_LABEL})\s*:\s*(.*)$", re.DOTALL)
# 074-9532445 Mary → the next person or sentence is a new line.
_PHONE_NEXT = re.compile(
    r"(?:\+353|\+44|0\d)[\d\s().-]{6,16}\d(?=\s+[A-ZÁÉÍÓÚ])"
)


def _parts(pattern: re.Pattern[str], text: str) -> list[str]:
    parts = [part.strip() for part in pattern.split(text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _split_at_phone(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in _PHONE_NEXT.finditer(text):
        left = text[start : match.end()].strip()
        if left:
            parts.append(left)
        start = match.end()
    rest = text[start:].strip()
    if rest:
        parts.append(rest)
    return parts or ([text] if text else [])


def split_reader_blocks(text: str) -> list[str]:
    """Break one smashed paragraph into the blocks already printed in it."""
    raw = (text or "").strip()
    if not raw:
        return []
    blocks: list[str] = []
    for part in _parts(_COLON_LABEL, raw):
        for bit in _parts(_BARE_LABEL, part):
            blocks.extend(_split_at_phone(bit))
    return blocks or [raw]


def parse_printed_label(text: str) -> tuple[str, str] | None:
    """Return (label, value) when the line is already a printed Label: value."""
    match = _LABEL_LINE.match((text or "").strip())
    if not match:
        return None
    label = match.group(1).strip()
    if len(label) > 60:
        return None
    return label, match.group(2).strip()
