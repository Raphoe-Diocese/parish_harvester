from __future__ import annotations

"""Compare a parish PDF's own text to the published OCR HTML.

This is how we catch missing notices without reading every page by eye.
It does **not** invent text. It only reports phrases that are already in
the PDF text layer and absent from the OCR page.
"""

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ocr.text_extract import extract_all_page_lines, page_is_sparse, page_text_char_count

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
PARISHES_DIR = DOCS_DIR / "parishes"
MEGA_DIR = DOCS_DIR / "mega_pdf"

_TAG_RE = re.compile(r"<[^>]+>")
_NOISE_RE = re.compile(r"[^a-z0-9áéíóúàèìòùâêîôûäëïöüñç'’\s]+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")

# Stitcher banners and chrome are not "missing bulletin text".
_SKIP_PHRASE = re.compile(
    r"parishpress|https?://|www\.|\b\S+\.(?:com|ie|org|net)\b|page \d+|back to|search text|"
    r"missing online only|downloadable pdf|do not have a",
    re.IGNORECASE,
)
_LETTER_DIGIT_RE = re.compile(r"([a-z])(\d)|(\d)([a-z])", re.IGNORECASE)
_URL_CHUNK_RE = re.compile(
    r"(?:https?://\S+|www\.\S+|\b\S+\.(?:com|ie|org|net)\S*)",
    re.IGNORECASE,
)


def normalize_for_compare(text: str) -> str:
    plain = _TAG_RE.sub(" ", html.unescape(text or ""))
    plain = _URL_CHUNK_RE.sub(" ", plain)
    plain = _LETTER_DIGIT_RE.sub(
        lambda m: f"{m.group(1) or m.group(3)} {m.group(2) or m.group(4)}",
        plain,
    )
    plain = _NOISE_RE.sub(" ", plain.lower())
    words = _SPACE_RE.sub(" ", plain).split()
    collapsed: list[str] = []
    for word in words:
        if collapsed and collapsed[-1] == word:
            continue
        collapsed.append(word)
    return " ".join(collapsed).strip()


def pdf_plain_text(pdf_path: Path) -> str:
    pages = extract_all_page_lines(pdf_path)
    if not pages:
        return ""
    return "\n".join("\n".join(lines) for lines in pages)


def ocr_html_plain_text(html_path: Path) -> str:
    if not html_path.is_file():
        return ""
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r'<div class="ocr-body"[^>]*>(.*?)</div>\s*<p class="note-box">',
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    fragment = match.group(1) if match else raw
    return _TAG_RE.sub("\n", html.unescape(fragment))


def missing_phrases(pdf_text: str, ocr_text: str, *, window: int = 8) -> list[str]:
    """Return PDF word-windows that do not appear in the OCR text."""
    pdf_words = normalize_for_compare(pdf_text).split()
    ocr_norm = f" {normalize_for_compare(ocr_text)} "
    if len(pdf_words) < window:
        phrase = " ".join(pdf_words)
        if phrase and f" {phrase} " not in ocr_norm and not _SKIP_PHRASE.search(phrase):
            return [phrase]
        return []

    missing: list[str] = []
    i = 0
    while i <= len(pdf_words) - window:
        phrase = " ".join(pdf_words[i : i + window])
        if _SKIP_PHRASE.search(phrase):
            i += 1
            continue
        if f" {phrase} " not in ocr_norm:
            distinctive = [w for w in phrase.split() if len(w) > 3]
            if distinctive and all(f" {w} " in ocr_norm for w in distinctive):
                i += 1
                continue
            missing.append(phrase)
            i += window
            continue
        i += 1

    collapsed: list[str] = []
    for phrase in missing:
        if collapsed and phrase in collapsed[-1]:
            continue
        if collapsed and collapsed[-1] in phrase:
            collapsed[-1] = phrase
            continue
        collapsed.append(phrase)
    return collapsed[:12]


@dataclass(frozen=True)
class FidelityRow:
    diocese: str
    key: str
    pdf_chars: int
    ocr_chars: int
    sparse_pdf: bool
    missing: list[str]

    @property
    def ok(self) -> bool:
        if self.sparse_pdf:
            return True
        return not self.missing


def check_parish_files(diocese: str, key: str, pdf_path: Path, ocr_path: Path) -> FidelityRow:
    pages = extract_all_page_lines(pdf_path) or []
    pdf_text = "\n".join("\n".join(lines) for lines in pages)
    ocr_text = ocr_html_plain_text(ocr_path)
    sparse = (not pages) or all(page_is_sparse(p) for p in pages)
    missing = [] if sparse else missing_phrases(pdf_text, ocr_text)
    return FidelityRow(
        diocese=diocese,
        key=key,
        pdf_chars=page_text_char_count(pdf_text.splitlines()),
        ocr_chars=len(normalize_for_compare(ocr_text)),
        sparse_pdf=sparse,
        missing=missing,
    )


def iter_parish_ocr_pairs(docs_dir: Path | None = None) -> list[tuple[str, str, Path, Path]]:
    root = (docs_dir or DOCS_DIR) / "parishes"
    pairs: list[tuple[str, str, Path, Path]] = []
    if not root.is_dir():
        return pairs
    for diocese_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for ocr_path in sorted(diocese_dir.glob("*-ocr.html")):
            key = ocr_path.name[: -len("-ocr.html")]
            pdf_path = diocese_dir / f"{key}.pdf"
            if not pdf_path.is_file():
                continue
            pairs.append((diocese_dir.name, key, pdf_path, ocr_path))
    return pairs


def scan_published_parishes(docs_dir: Path | None = None) -> list[FidelityRow]:
    rows: list[FidelityRow] = []
    for diocese, key, pdf_path, ocr_path in iter_parish_ocr_pairs(docs_dir):
        rows.append(check_parish_files(diocese, key, pdf_path, ocr_path))
    return rows


def scan_mega_slices(docs_dir: Path | None = None) -> list[FidelityRow]:
    """Compare mega-PDF page ranges to the parish OCR even when no slice file exists."""
    from ocr.parish_pages import slice_pdf_pages

    docs = docs_dir or DOCS_DIR
    rows: list[FidelityRow] = []
    for index_path in sorted((docs / "mega_pdf").glob("*_mega_bulletin.pages.json")):
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        mega_name = str(payload.get("pdf") or index_path.name.replace(".pages.json", ".pdf"))
        mega_pdf = index_path.with_name(mega_name)
        if not mega_pdf.is_file():
            continue
        diocese = mega_name.replace("_mega_bulletin.pdf", "")
        parishes = payload.get("parishes") or {}
        for key, info in sorted(parishes.items()):
            start = int(info.get("start_page") or 0)
            end = int(info.get("end_page") or 0)
            if not (start and end):
                continue
            ocr_path = docs / "parishes" / diocese / f"{key}-ocr.html"
            if not ocr_path.is_file():
                continue
            pdf_path = docs / "parishes" / diocese / f"{key}.pdf"
            if pdf_path.is_file() and pdf_path.stat().st_size > 2048:
                rows.append(check_parish_files(diocese, key, pdf_path, ocr_path))
                continue
            sliced = slice_pdf_pages(mega_pdf, start, end)
            if not sliced:
                continue
            tmp = index_path.with_name(f"_fid_{key}.pdf")
            try:
                tmp.write_bytes(sliced)
                rows.append(check_parish_files(diocese, key, tmp, ocr_path))
            finally:
                tmp.unlink(missing_ok=True)
    return rows


def format_report(rows: list[FidelityRow]) -> str:
    failed = [r for r in rows if not r.ok]
    lines = [
        f"Checked {len(rows)} parish PDF/OCR pairs. "
        f"{len(rows) - len(failed)} match. {len(failed)} missing PDF text."
    ]
    for row in failed:
        lines.append(f"- {row.diocese}/{row.key}: {len(row.missing)} gap(s)")
        for phrase in row.missing[:3]:
            lines.append(f"    … {phrase}")
    return "\n".join(lines)
