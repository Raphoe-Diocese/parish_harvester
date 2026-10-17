"""Repeatable spacing pass for bulletin text.

Runs on every diocese after the older joins. It only changes patterns
that were read on the live pages. It does not invent names, Mass times,
or Irish spelling.
"""
from __future__ import annotations

import re

# ssii, iinn: a photo cipher made of doubled letters. Not a word.
_DOUBLED_PAIRS = re.compile(r"^(([A-Za-z])\2){2,}$")
# lsdkjflas: six consonants in a row. strengths stops at five.
_CONSONANT_MASH = re.compile(r"[bcdfghjklmnpqrstvwxyz]{6}", re.I)
_FADA = re.compile(r"[áéíóúÁÉÍÓÚ]")


def _drop_token(token: str) -> bool:
    if "@" in token or "http" in token.lower() or token.lower().startswith("www"):
        return False
    if re.search(r"\d", token):
        return False
    if _FADA.search(token):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", token)
    if not letters:
        return False
    if _DOUBLED_PAIRS.match(letters):
        return True
    return bool(_CONSONANT_MASH.search(letters))


def readable_pass(text: str) -> str:
    """Space glued words and drop proved scraps. Leave a normal sentence."""
    if not text:
        return text or ""
    cleaned = text
    cleaned = re.sub(
        r"\b(\d{1,2})_([A-Za-z]{3,})_(\d{4})\b",
        r"\1 \2 \3",
        cleaned,
    )
    # PPTel → PP Tel. Does not split MACKEY or a phone.
    cleaned = re.sub(r"\b([A-Z]{2,})([A-Z][a-z]{2,})\b", r"\1 \2", cleaned)
    cleaned = re.sub(r"\bKILL\s+ARNEY\b", "KILLARNEY", cleaned)
    cleaned = re.sub(r"\bNEW\s+SLETT\s+ER\b", "NEWSLETTER", cleaned)
    cleaned = re.sub(r"\bWebsi\s+te\b", "Website", cleaned, flags=re.I)
    cleaned = re.sub(r"\bHfyou\b", "If you", cleaned)
    kept = [tok for tok in cleaned.split() if not _drop_token(tok)]
    cleaned = " ".join(kept)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()
