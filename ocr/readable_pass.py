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
# Proved photo leftovers. Not real bulletin words. DARKNE is the Cloyne banner scrap.
_PHOTO_TOKEN = frozenset({"scedi", "yii", "iito", "darkne"})
# Sy)"IN: a letter, a quote or bracket, then another letter. Not O'Brien or Mary's.
_MASHED_MARK = re.compile(r"[A-Za-z][)\"]+[A-Za-z]")
# AAAAs: four of the same letter. A normal word does not do that.
_STUTTER = re.compile(r"^([A-Za-z])\1{3,}[A-Za-z]?$")


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
    if _MASHED_MARK.search(token):
        return True
    if letters.lower() in _PHOTO_TOKEN:
        return True
    if _DOUBLED_PAIRS.match(letters):
        return True
    if _STUTTER.match(letters):
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
    cleaned = re.sub(r"\bIfyou\b", "If you", cleaned)
    cleaned = re.sub(r"\bSires\s+[‘'’]?Prisoner", "Prisoner", cleaned)
    cleaned = re.sub(r"\bDarfil\b", "", cleaned)
    # Dunfanaghy photo line. "aon" on its own is Irish and stays.
    cleaned = re.sub(
        r"\bSE\s+a\s+aon\b(?:\s+\S+){0,8}\s+(?=There\s+are\s+two\s+sides\b)",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\bRemembrance\s+I\s+I\s+to\b", "Remembrance to", cleaned)
    cleaned = re.sub(r"\bi\s+SEFr\.", "Fr.", cleaned)
    cleaned = re.sub(
        r'\b(\d{1,2})"\s+(Sunday|October)\b',
        r"\1th \2",
        cleaned,
    )
    cleaned = re.sub(r"\b2\s+(?=ardara@)", "", cleaned)
    cleaned = re.sub(r"\b0\s+God\b", "O God", cleaned)
    cleaned = re.sub(
        r"\bGlory\s+te\s+Ged\s+in\s+the\s+highest\b",
        "Glory to God in the highest",
        cleaned,
    )
    cleaned = re.sub(
        r"\bseated\s+al\s+the\s+right\b",
        "seated at the right",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\b1\.00m\.", "1.00pm", cleaned)
    cleaned = re.sub(
        r"\bparishioners we offer ours\s+parishioners we offer our\b",
        "parishioners we offer our",
        cleaned,
    )
    cleaned = re.sub(r"\brecentlyrecently\b", "recently", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+!\s+", " ", cleaned)
    kept = [tok for tok in cleaned.split() if not _drop_token(tok)]
    cleaned = " ".join(kept)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()
