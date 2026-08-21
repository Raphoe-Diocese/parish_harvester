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
    path = Path(pdf_path)
    if not path.is_file():
        return None

    try:
        reader = PdfReader(str(path))
    except Exception:
        return None

    if not reader.pages:
        return None

    page_lines: list[list[str]] = []
    total_chars = 0

    for page in reader.pages:
        raw = (page.extract_text() or "").strip()
        total_chars += len(raw)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        page_lines.append(lines)

    if total_chars < MIN_TOTAL_CHARS:
        return None

    non_empty = [lines for lines in page_lines if lines]
    if not non_empty:
        return None

    avg_chars = total_chars / max(len(reader.pages), 1)
    if avg_chars < MIN_CHARS_PER_PAGE:
        return None

    return page_lines
