from __future__ import annotations

"""Tier 0: extract text from born-digital PDFs before any vision OCR.

Returns None when the PDF looks scanned or image-only so callers can fall back
to Mistral / Gemini / OpenAI.
"""

from pathlib import Path

from PyPDF2 import PdfReader

# Heuristic thresholds — tuned for parish newsletter PDFs (Word/InDesign exports).
MIN_CHARS_PER_PAGE = 80
MIN_TOTAL_CHARS = 200


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
