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


def _lines_from_raw(raw: str | None) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _extract_pypdf_pages(path: Path) -> list[list[str]] | None:
    try:
        reader = PdfReader(str(path))
    except Exception:
        return None
    if not reader.pages:
        return None
    return [_lines_from_raw(page.extract_text()) for page in reader.pages]


def _extract_pymupdf_pages(path: Path) -> list[list[str]] | None:
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        doc = pymupdf.open(str(path))
    except Exception:
        return None
    try:
        if doc.page_count < 1:
            return None
        return [_lines_from_raw(page.get_text("text")) for page in doc]
    finally:
        doc.close()


def pick_richer_page_lines(
    first: list[list[str]] | None,
    second: list[list[str]] | None,
) -> list[list[str]] | None:
    """Keep the fuller text layer per page (PyMuPDF often sees boxed notices)."""
    if not first:
        return second
    if not second:
        return first
    count = max(len(first), len(second))
    out: list[list[str]] = []
    for idx in range(count):
        a = first[idx] if idx < len(first) else []
        b = second[idx] if idx < len(second) else []
        out.append(a if page_text_char_count(a) >= page_text_char_count(b) else b)
    return out


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

    total_chars = sum(page_text_char_count(lines) for lines in page_lines)
    if total_chars < MIN_TOTAL_CHARS:
        return None

    non_empty = [lines for lines in page_lines if lines]
    if not non_empty:
        return None

    avg_chars = total_chars / max(len(page_lines), 1)
    if avg_chars < MIN_CHARS_PER_PAGE:
        return None

    return page_lines


def extract_all_page_lines(pdf_path: str | Path) -> list[list[str]] | None:
    """Return one line-list per page whenever the PDF opens.

    Unlike :func:`extract_text_pages`, this does **not** reject mixed megas
    that have image-only pages. Callers decide per page with
    :func:`page_is_sparse`.

    PyMuPDF is tried first and merged with PyPDF2 so boxed notices (the
    Enda / Edna Hill acknowledgement style) are not lost when one reader
    skips a text frame.
    """
    path = Path(pdf_path)
    if not path.is_file():
        return None
    return pick_richer_page_lines(_extract_pymupdf_pages(path), _extract_pypdf_pages(path))


def all_pages_have_embedded_text(pages: list[list[str]] | None) -> bool:
    """True when every page looks like a real bulletin body, not a banner."""
    return bool(pages) and not any(page_is_sparse(p) for p in pages)


def prefer_embedded_page_text(
    pdf_path: str | Path,
    pages_text: list[list[str]] | None,
) -> list[list[str]] | None:
    """Keep vision/sparse OCR only on image pages; use PDF text everywhere else.

    Born-digital parish pages already have the real wording (dates, names,
    one-line notices). Vision OCR of a stitched mega can drop a column or
    turn ``22nd`` into ``2nd``. This costs no API tokens.
    """
    embedded = extract_all_page_lines(pdf_path)
    if not embedded:
        return pages_text
    if not pages_text:
        return embedded

    count = max(len(pages_text), len(embedded))
    merged: list[list[str]] = []
    for idx in range(count):
        vision = pages_text[idx] if idx < len(pages_text) else []
        native = embedded[idx] if idx < len(embedded) else []
        if not page_is_sparse(native):
            merged.append(native)
        else:
            merged.append(vision)
    return merged

