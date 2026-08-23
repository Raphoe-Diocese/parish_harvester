from __future__ import annotations

"""Compare parish PDF text against published *-ocr.html fragments.

Used to catch vision-OCR holes (dropped notices, 22nd -> 2nd) after a harvest
without inventing bulletin text. Stitcher URLs and mega-index filler are ignored.
"""

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
PARISHES_DIR = DOCS_DIR / "parishes"

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_LETTER_DIGIT = re.compile(r"([A-Za-zÀ-ÿ])(\d)")
_DIGIT_LETTER = re.compile(r"(\d)([A-Za-zÀ-ÿ])")
_ABBREV_DOTS = re.compile(r"\b(?:[A-Za-z]\.){2,}")
_SKIP_PHRASE = re.compile(
    r"parishpress|https?://|www\.|\bpage\s+\d+\b|missing\s+online\s+only|downloadable\s+pdf",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^A-Za-zÀ-ÿ0-9'\s]+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FidelityRow:
    diocese: str
    parish_key: str
    ok: bool
    missing: list[str]
    pdf_chars: int
    ocr_chars: int


def normalize_for_compare(text: str) -> str:
    """Strip tags/URLs, split letter-digit boundaries, collapse duplicate words."""
    cleaned = _TAG_RE.sub(" ", text or "")
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _ABBREV_DOTS.sub(lambda m: m.group(0).replace(".", ""), cleaned)
    cleaned = _LETTER_DIGIT.sub(r"\1 \2", cleaned)
    cleaned = _DIGIT_LETTER.sub(r"\1 \2", cleaned)
    cleaned = _NON_WORD.sub(" ", cleaned)
    words = _SPACE_RE.sub(" ", cleaned).strip().lower().split()
    collapsed: list[str] = []
    for word in words:
        if collapsed and collapsed[-1] == word:
            continue
        collapsed.append(word)
    return " ".join(collapsed)


def pdf_plain_text(pdf_path: Path | str) -> str:
    from ocr.text_extract import extract_all_page_lines

    pages = extract_all_page_lines(pdf_path) or []
    raw = "\n".join("\n".join(lines) for lines in pages)
    return normalize_for_compare(raw)


def ocr_html_plain_text(html_path: Path | str) -> str:
    raw = Path(html_path).read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r'<div class="ocr-body"[^>]*>\s*(.*?)\s*</div>\s*<p class="note-box">',
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
            raw,
            re.IGNORECASE | re.DOTALL,
        )
    fragment = match.group(1) if match else raw
    return normalize_for_compare(fragment)


def _skip_phrase(phrase: str) -> bool:
    return bool(_SKIP_PHRASE.search(phrase or ""))


def missing_phrases(pdf_text: str, ocr_text: str, window: int = 8) -> list[str]:
    """Return 8-word PDF windows that are missing from OCR.

    If the exact window is absent, accept the window when every word longer
    than 3 characters is present in the OCR (parish-name glue / wrap noise).
    """
    pdf_words = (pdf_text or "").split()
    ocr_norm = ocr_text or ""
    ocr_words = set(ocr_norm.split())
    if not pdf_words:
        return []

    def _accepted(words: list[str], phrase: str) -> bool:
        if _skip_phrase(phrase):
            return True
        if phrase and phrase in ocr_norm:
            return True
        distinctive = [w for w in words if len(w) > 3]
        return bool(distinctive) and all(w in ocr_words for w in distinctive)

    if len(pdf_words) < window:
        phrase = " ".join(pdf_words)
        return [] if _accepted(pdf_words, phrase) else [phrase]

    missing: list[str] = []
    seen: set[str] = set()
    for i in range(0, len(pdf_words) - window + 1):
        words = pdf_words[i : i + window]
        phrase = " ".join(words)
        if _accepted(words, phrase):
            continue
        if phrase not in seen:
            seen.add(phrase)
            missing.append(phrase)
    return missing


def check_parish_files(
    pdf_path: Path | str,
    ocr_html_path: Path | str,
    *,
    diocese: str = "",
    parish_key: str = "",
) -> FidelityRow:
    pdf = Path(pdf_path)
    ocr = Path(ocr_html_path)
    pdf_text = pdf_plain_text(pdf) if pdf.exists() else ""
    ocr_text = ocr_html_plain_text(ocr) if ocr.exists() else ""
    if not pdf_text:
        missing = ["no embedded pdf text"] if ocr_text else ["missing pdf and ocr"]
        ok = False
    else:
        missing = missing_phrases(pdf_text, ocr_text)
        ok = not missing
    return FidelityRow(
        diocese=diocese or pdf.parent.name,
        parish_key=parish_key or pdf.stem,
        ok=ok,
        missing=missing,
        pdf_chars=len(pdf_text),
        ocr_chars=len(ocr_text),
    )


def scan_published_parishes(parishes_root: Path | None = None) -> list[FidelityRow]:
    root = Path(parishes_root) if parishes_root else PARISHES_DIR
    rows: list[FidelityRow] = []
    if not root.exists():
        return rows
    for diocese_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for pdf_path in sorted(diocese_dir.glob("*.pdf")):
            key = pdf_path.stem
            ocr_path = diocese_dir / f"{key}-ocr.html"
            if not ocr_path.exists():
                continue
            rows.append(
                check_parish_files(
                    pdf_path,
                    ocr_path,
                    diocese=diocese_dir.name,
                    parish_key=key,
                )
            )
    return rows


def scan_mega_slices(parishes_root: Path | None = None) -> list[FidelityRow]:
    return scan_published_parishes(parishes_root)


def format_report(rows: list[FidelityRow]) -> str:
    total = len(rows)
    ok_n = sum(1 for row in rows if row.ok)
    lines = [f"OCR fidelity: {ok_n}/{total} parishes match embedded PDF text."]
    gaps = [row for row in rows if not row.ok]
    if not gaps:
        return "\n".join(lines)
    lines.append("Gaps:")
    for row in gaps:
        sample = "; ".join(row.missing[:3]) if row.missing else "(no phrases)"
        lines.append(f"  {row.diocese}/{row.parish_key}: {sample}")
    return "\n".join(lines)
