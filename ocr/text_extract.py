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
    "a", "i", "o", "am", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
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
    "am", "pm", "rev", "lit", "tel",
})
_ACCENTED = re.compile(r"[áéíóúÁÉÍÓÚ]")
_VOWEL = re.compile(r"[aeiouáéíóú]", re.I)
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{3}", re.I)


_SHORT_OK = frozenset({
    "a", "i", "o", "am", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
    "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    "na", "ar", "ag", "le", "mo", "sa",
})
_ABBREV_OK = frozenset({
    "fr", "pp", "st", "cc", "am", "pm", "rev",
    "gal", "ps", "lk", "jn", "mt", "mk",
})
# A short word with none of these is not ordinary English. Used only to
# spot photo leftovers such as jeboi. Real words are still kept unless
# they sit in a run of leftovers.
_COMMON_TRIGRAM = frozenset({
    "the", "and", "ing", "ion", "ent", "tio", "for", "her", "ter", "ate",
    "ver", "all", "wit", "thi", "tha", "hat", "his", "ere", "rea", "com",
    "ome", "man", "any", "ive", "pro", "res", "est", "ati", "str", "tre",
    "day", "sun", "mas", "ass", "par", "ari", "ris", "ish", "chu", "hur",
    "rch", "tim", "ime", "wee", "eek", "ord", "pri", "rie", "not", "ice",
    "ple", "lea", "eas", "ase", "wil", "ill", "hav", "ave", "bee", "een",
    "fro", "rom", "whi", "hic", "ich", "out", "int", "nto", "ove", "als",
    "onl", "nly", "mor", "som", "eve", "sid", "ide", "des", "lov", "vin",
    "hol", "oly", "cro", "ros", "mem", "ory", "can", "dle", "sto", "tor",
    "who", "ear", "yea", "ann", "way", "she", "ash",
})
_GOOD_ENDING = re.compile(
    r"(?:ed|es|er|ly|ing|ion|day|ous|ent|ant|est|ist|ity|ate|ful|ness|ment|ments|ship|th|mas)$",
    re.I,
)


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


# "gd" inside kingdom is a real word. egdirae has gd that is not after n.
_BAD_BIGRAM = re.compile(
    r"(?<!n)gd|gk|gq|gx|jx|qx|vx|zx|bq|cx|fq|hx|kx|pq|qj|qk|qy|qz|xj",
    re.I,
)


def _junk_kind(token: str) -> str:
    """'hard' photo scrap, 'soft' odd token, or '' for a real word.

    Soft tokens are removed only when they sit beside a hard scrap.
    Two ordinary words that merely look odd are left alone.
    """
    if re.fullmatch(r"[&/|~–—.+]+", token or ""):
        return ""
    low_all = (token or "").lower()
    if "@" in (token or "") or "http" in low_all or low_all.startswith("www"):
        return ""
    if _ACCENTED.search(token or ""):
        return ""
    if re.search(r"[{}|\\^<>]", token or ""):
        return "hard"
    if re.search(r"\d", token or ""):
        return ""
    letters = _letters_of(token)
    if not letters:
        return ""
    low = letters.lower()
    if low in _KEEP_WORDS or low in _ABBREV_OK or low in _SHORT_OK:
        return ""
    if token[:1].isupper() and len(letters) >= 3 and _VOWEL.search(low):
        return ""
    if not re.search(r"[bcdfghjklmnpqrstvwxyz]", low):
        return "hard"
    if _BAD_BIGRAM.search(low):
        return "hard"
    if len(letters) <= 2:
        return "hard"
    if token[:1].isupper() or len(letters) > 8 or _GOOD_ENDING.search(low):
        return ""
    grams = {low[i:i + 3] for i in range(max(0, len(low) - 2))}
    if len(letters) >= 4 and grams and not grams & _COMMON_TRIGRAM:
        return "soft"
    if len(letters) == 3:
        return "soft"
    return ""


def _cluster_transparent(token: str) -> bool:
    """A single digit, a mark, or a two-letter capital between scraps.

    It stays. Real words such as the, of, and new split the run, so a
    sentence is not pulled into the scrap beside it.
    """
    if re.fullmatch(r"\d", token or ""):
        return True
    letters = _letters_of(token)
    if not letters:
        return True
    return letters.isupper() and len(letters) <= 2


def drop_photo_junk_tokens(text: str) -> str:
    """Drop a photo leftover only when it sits beside another leftover.

    One odd token in a real sentence stays. Irish with fadas stays.
    Phones, emails and capital names stay.
    """
    tokens = (text or "").split()
    if len(tokens) < 4:
        return text or ""
    kinds = [_junk_kind(tok) for tok in tokens]
    drop = [False] * len(tokens)
    i = 0
    while i < len(tokens):
        if not kinds[i] and not _cluster_transparent(tokens[i]):
            i += 1
            continue
        j = i
        while j < len(tokens) and (kinds[j] or _cluster_transparent(tokens[j])):
            j += 1
        run = [k for k in range(i, j) if kinds[k]]
        hard = [k for k in run if kinds[k] == "hard"]
        strong = [
            k for k in hard
            if re.search(r"[{}|\\^<>]", tokens[k])
            or _BAD_BIGRAM.search(_letters_of(tokens[k]))
            or (
                _letters_of(tokens[k])
                and not re.search(
                    r"[bcdfghjklmnpqrstvwxyz]", _letters_of(tokens[k]), re.I
                )
            )
        ]
        # A symbol, a nonsense bigram, or a vowel-only scrap can take the
        # odd tokens beside it. A stray "n" or "HT" must not.
        if strong and len(run) >= 2:
            for k in run:
                drop[k] = True
        elif len(hard) >= 2:
            for k in hard:
                drop[k] = True
        else:
            for k in strong:
                drop[k] = True
        i = j
    if not any(drop):
        return text
    return " ".join(tok for tok, gone in zip(tokens, drop) if not gone)


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
