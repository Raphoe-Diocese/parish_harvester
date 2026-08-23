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
        if nat and not page_is_sparse(nat):
            out.append(nat)
        else:
            out.append(vis)
    return out
