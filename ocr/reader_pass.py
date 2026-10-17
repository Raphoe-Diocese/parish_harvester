"""One reader layout for every parish bulletin.

Runs on the text of every diocese. It does not look up a parish name
and it does not invent words. Only a known bulletin label is split out.
A phone number ends a line. The next name or sentence starts the next line.
"""

from __future__ import annotations

import re

# Longer phrases first so "Parish Office" wins over a shorter word.
_KNOWN_LABELS = (
    "Parish Child Safeguarding Liaisons",
    "Community Notices",
    "Recently Deceased",
    "Parish Newsletter",
    "Sunday Collection",
    "Parish Notices",
    "Useful numbers",
    "Mass Bookings",
    "Parish Office",
    "Month's Mind",
    "Months Mind",
    "Mass times",
    "Instagram",
    "Telephone",
    "Facebook",
    "Webpage",
    "YouTube",
    "Twitter",
    "E-mail",
    "Email",
    "Web",
    "Tel",
)
# "Annagry Parish Pastoral Council:" keeps the words already in front of it.
_PASTORAL = r"(?:[A-ZÁÉÍÓÚ][\w'’.-]+\s+){0,3}Pastoral\s+Council"
_LABEL = "|".join(re.escape(label) for label in _KNOWN_LABELS) + "|" + _PASTORAL
# Split only where the known label itself is followed by a colon.
_COLON_LABEL = re.compile(rf"(?<![A-Za-zÁÉÍÓÚáéíóú])(?:{_LABEL})\s*:", re.IGNORECASE)
_BARE_LABEL = re.compile(
    r"(?<![A-Za-zÁÉÍÓÚáéíóú])(?:Charity\s+No\.|Parish\s+Child\s+Safeguarding(?:\s+Liaisons)?)\b",
    re.IGNORECASE,
)
_LABEL_LINE = re.compile(rf"^({_LABEL})\s*:\s*(.*)$", re.IGNORECASE | re.DOTALL)
# 074-9532445 Mary → the next person or sentence is a new line.
_PHONE_NEXT = re.compile(
    r"(?:\+353|\+44|0\d)[\d\s().-]{6,16}\d(?=\s+[A-ZÁÉÍÓÚ])"
)


def _split_at(pattern: re.Pattern[str], text: str) -> list[str]:
    """Split before each match. The match stays with the text that follows it."""
    parts: list[str] = []
    start = 0
    for match in pattern.finditer(text):
        if match.start() < start:
            continue
        left = text[start : match.start()].strip(" \t")
        if left:
            parts.append(left)
        start = match.start()
    rest = text[start:].strip(" \t")
    if rest:
        parts.append(rest)
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
    for part in _split_at(_COLON_LABEL, raw):
        for bit in _split_at(_BARE_LABEL, part):
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
