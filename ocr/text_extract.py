from __future__ import annotations

"""Tier 0: extract text from born-digital PDFs before any vision OCR.

Returns None when the PDF looks scanned or image-only so callers can fall back
to Mistral / Gemini / OpenAI.
"""

import re
from pathlib import Path

from PyPDF2 import PdfReader

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# Heuristic thresholds — tuned for parish newsletter PDFs (Word/InDesign exports).
MIN_CHARS_PER_PAGE = 80
MIN_TOTAL_CHARS = 200
# A real bulletin page is thousands of characters. Stitcher banners are a
# short name + URL (often 40–150 chars) sitting on an image-only page.
SPARSE_PAGE_CHARS = 200
BANNER_ONLY_CHARS = 400


def page_text_char_count(lines: list[str] | None) -> int:
    return len("\n".join(lines or []).strip())


def page_is_sparse(lines: list[str] | None) -> bool:
    """True when a page looks like a stitcher banner, not a real bulletin body."""
    text = "\n".join(ln.strip() for ln in (lines or []) if str(ln).strip()).strip()
    if not text:
        return True
    if len(text) < SPARSE_PAGE_CHARS:
        return True
    nonempty = [ln for ln in text.splitlines() if ln.strip()]
    if (
        len(text) < BANNER_ONLY_CHARS
        and len(nonempty) <= 4
        and _URL_RE.search(text)
    ):
        return True
    return False


def _lines_from_raw(raw: str) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _extract_pypdf_pages(pdf_path: str | Path) -> list[list[str]] | None:
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return None
    if not reader.pages:
        return None
    return [_lines_from_raw(page.extract_text() or "") for page in reader.pages]


def _extract_pymupdf_pages(pdf_path: str | Path) -> list[list[str]] | None:
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:
        return None
    try:
        if doc.page_count == 0:
            return None
        return [_lines_from_raw(page.get_text("text") or "") for page in doc]
    finally:
        try:
            doc.close()
        except Exception:
            pass


def pick_richer_page_lines(
    first: list[list[str]] | None,
    second: list[list[str]] | None,
) -> list[list[str]]:
    """Per page, keep the line list with more characters."""
    first = list(first or [])
    second = list(second or [])
    n = max(len(first), len(second))
    out: list[list[str]] = []
    for i in range(n):
        a = first[i] if i < len(first) else []
        b = second[i] if i < len(second) else []
        out.append(a if page_text_char_count(a) >= page_text_char_count(b) else b)
    return out


def extract_all_page_lines(pdf_path: str | Path) -> list[list[str]] | None:
    """Return per-page lines from PyMuPDF + PyPDF2, keeping the richer page.

    Does not reject mixed megas (image pages + born-digital pages).
    """
    path = Path(pdf_path)
    if not path.is_file():
        return None
    pymu = _extract_pymupdf_pages(path)
    pypdf = _extract_pypdf_pages(path)
    if not pymu and not pypdf:
        return None
    return pick_richer_page_lines(pymu, pypdf)


def extract_text_pages(pdf_path: str | Path) -> list[list[str]] | None:
    """Return per-page line lists if the PDF has enough embedded text.

    Parameters
    ----------
    pdf_path:
        Path to a PDF file.

    Returns
    -------
    list[list[str]] | None
        One list of lines per page, or ``None`` if text density is too low.
    """
    page_lines = extract_all_page_lines(pdf_path)
    if not page_lines:
        return None

    total_chars = sum(len("\n".join(lines)) for lines in page_lines)
    if total_chars < MIN_TOTAL_CHARS:
        return None

    non_empty = [lines for lines in page_lines if lines]
    if not non_empty:
        return None

    avg_chars = total_chars / max(len(page_lines), 1)
    if avg_chars < MIN_CHARS_PER_PAGE:
        return None

    return page_lines


def all_pages_have_embedded_text(pages: list[list[str]] | None) -> bool:
    """True iff *pages* is non-empty and no page looks sparse/banner-only."""
    if not pages:
        return False
    return all(not page_is_sparse(lines) for lines in pages)


# Words that are real in a bulletin. A photo page is mostly other scraps.
_KEEP_WORDS = frozenset({
    "a", "i", "am", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
    "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    "the", "and", "for", "you", "can", "now", "all", "who", "our", "are", "was",
    "not", "but", "his", "her", "has", "had", "any", "its", "out", "may", "let",
    "one", "two", "per", "new", "old", "day", "god", "see", "ask", "na", "ar",
    "ag", "le", "mo", "sa", "gan", "mar", "se", "si", "ni", "ma", "mas", "fiu",
    "aon", "don", "den", "seo", "sin", "agus", "ach",
    "mass", "masses", "sunday", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "parish", "church", "priest", "office", "email",
    "phone", "vigil", "funeral", "anniversary", "anniversaries", "intention",
    "intentions", "collection", "newsletter", "bulletin", "rosary", "adoration",
    "baptism", "confession", "confessions", "novena", "sympathy", "family",
    "families", "please", "welcome", "thank", "thanks", "holy", "time", "times",
    "ordinary", "week", "morning", "evening", "night", "this", "that", "with",
    "from", "your", "have", "will", "been", "were", "they", "them", "their",
    "there", "here", "when", "what", "which", "after", "before", "about",
    "into", "over", "also", "only", "more", "some", "than", "then", "every",
    "each", "other", "people", "lord", "jesus", "mary", "saint", "rest",
    "peace", "soul", "souls", "dead", "deceased", "recently", "month", "mind",
    "pray", "prayer", "prayers", "notice", "notices", "news", "community",
    "bingo", "contact", "website", "online", "donation", "donations",
    "safeguarding", "children", "child", "october", "september", "november",
    "december", "january", "february", "march", "april", "june", "july",
    "august", "may", "sides", "story", "candle", "remembrance", "cross",
    "coming", "memory", "two", "are", "there", "every", "both", "such",
    "would", "could", "should", "today", "open", "closed", "special",
    "private", "public", "reading", "gospel", "fr", "pp", "st", "cc", "rip",
    "am", "pm", "rev",
})
_ACCENTED = re.compile(r"[áéíóúÁÉÍÓÚ]")
_VOWEL = re.compile(r"[aeiouáéíóú]", re.I)
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{3}", re.I)


_SHORT_OK = frozenset({
    "a", "i", "am", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
    "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    "na", "ar", "ag", "le", "mo", "sa",
})
_ABBREV_OK = frozenset({"fr", "pp", "st", "cc", "am", "pm", "rev"})


def _letters_of(token: str) -> str:
    return re.sub(r"[^A-Za-zÀ-ÿ]", "", token or "")


def _token_is_scrap(token: str) -> bool:
    """A one-to-three letter leftover, not a real short word or Fr/PP/St."""
    if re.search(r"\d", token or ""):
        return False
    if re.fullmatch(r"[&/|~–—.+]+", token or ""):
        return False
    if _ACCENTED.search(token or ""):
        return False
    letters = _letters_of(token)
    if not letters or len(letters) > 3:
        return False
    low = letters.lower()
    if low in _ABBREV_OK or low in _KEEP_WORDS or low in _SHORT_OK:
        return False
    return True


def _token_is_photo_junk(token: str) -> bool:
    """A scrap from a photographed page, not a word, name, phone or Irish."""
    if re.fullmatch(r"[&/|~–—.+]+", token or ""):
        return False
    low_all = (token or "").lower()
    if "@" in token or "http" in low_all or low_all.startswith("www."):
        return False
    if _ACCENTED.search(token or ""):
        return False
    if re.search(r"\d", token or ""):
        return False
    if re.search(r"[{}|\\^]", token or ""):
        return True
    if _token_is_scrap(token):
        return True
    letters = _letters_of(token)
    if not letters:
        return True
    low = letters.lower()
    if low in _KEEP_WORDS:
        return False
    if token[:1].isupper() and len(letters) >= 3 and _VOWEL.search(low):
        return False
    # On a photo line only: short unknown leftovers, not real words like programme.
    if token[:1].islower() and (
        len(letters) <= 7 or not _VOWEL.search(low) or _CONSONANT_RUN.search(low)
    ):
        return True
    return False


def drop_photo_junk_tokens(text: str) -> str:
    """On a photographed line, keep the real words and drop the scraps.

    A normal sentence is left as it is. Irish with fadas is left as it is.
    A line is only treated as a photo when it has several short scraps.
    """
    tokens = (text or "").split()
    if len(tokens) < 4:
        return text or ""
    if sum(1 for tok in tokens if _ACCENTED.search(tok)) >= 2:
        return text
    scraps = sum(1 for tok in tokens if _token_is_scrap(tok))
    # Three scraps in a long parish notice is normal. A photo line is
    # mostly scraps (about one in six tokens, or more).
    if scraps < 3 or scraps / len(tokens) < 0.15:
        return text
    kept = [tok for tok in tokens if not _token_is_photo_junk(tok)]
    return " ".join(kept)


def page_text_is_garbage(lines: list[str] | None) -> bool:
    """True when a page is mostly photo scraps, not a readable bulletin."""
    tokens = " ".join(lines or []).split()
    if len(tokens) < 12:
        return False
    if sum(1 for tok in tokens if _ACCENTED.search(tok)) >= 4:
        return False
    scraps = sum(
        1
        for tok in tokens
        if _token_is_scrap(tok) or re.search(r"[{}|\\^]|ffi!", tok)
    )
    return scraps / len(tokens) >= 0.18


def prefer_embedded_page_text(
    pdf_path: str | Path,
    pages_text: list[list[str]] | None,
) -> list[list[str]]:
    """Replace vision OCR with native PDF text on pages that are not sparse."""
    native = extract_all_page_lines(pdf_path) or []
    vision = [list(lines or []) for lines in (pages_text or [])]
    n = max(len(native), len(vision))
    out: list[list[str]] = []
    for i in range(n):
        nat = native[i] if i < len(native) else []
        vis = vision[i] if i < len(vision) else []
        if nat and not page_is_sparse(nat) and not page_text_is_garbage(nat):
            out.append(nat)
        elif vis:
            out.append(vis)
        else:
            out.append(nat)
    return out
