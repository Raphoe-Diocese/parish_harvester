from __future__ import annotations

"""Fill mega-PDF pages whose embedded text is only a stitcher banner.

A mixed mega PDF can pass Tier 0 overall (thousands of chars on other
pages) while an image-only parish page keeps just the 9pt name + URL
overlay. Vision OCR of the whole file can miss the same page. Re-OCR
those sparse pages from the rendered mega-PDF image and reuse that HTML
everywhere (diocese viewer + parish slice).
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ocr.text_extract import page_is_sparse, page_text_char_count

_PAGE_MARK_RE = re.compile(
    r"(?:<hr\s*/?>\s*)?"
    r"(?:<p\s+class=\"page-label\"[^>]*>|<p\b[^>]*>|<h[1-6]\b[^>]*>)"
    r"\s*Page\s+(\d+)\s*"
    r"</(?:p|h[1-6])>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _plain(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment or "")
    return re.sub(r"\s+", " ", text).strip()


_ALREADY_HAS_BODY_RE = re.compile(
    r"mass\s+times|weekend\s+mass|aifrinn|recent(?:ly)?\s+deceased|"
    r"missing\s*(?:&|&amp;)\s*online|anniversar",
    re.IGNORECASE,
)
_SINGLE_TOKEN_RE = re.compile(r"\S+")


def page_html_is_sparse(html_fragment: str) -> bool:
    """True when a page's OCR HTML is banner/masthead-only."""
    plain = _plain(html_fragment)
    if _ALREADY_HAS_BODY_RE.search(plain):
        return False
    return page_is_sparse(plain.splitlines())


def ocr_lines_look_usable(lines: list[str] | None) -> bool:
    """Reject decorative-scan garbage (lots of one-character tokens)."""
    text = "\n".join(lines or []).strip()
    if len(text) < 250:
        return False
    tokens = _SINGLE_TOKEN_RE.findall(text)
    if not tokens:
        return False
    singles = sum(1 for tok in tokens if len(tok) == 1)
    if singles / len(tokens) > 0.22:
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    if letters < 180:
        return False
    return True


def split_ocr_html_pages(fragment: str) -> list[tuple[int, str]]:
    """Split OCR HTML on ``Page N`` markers (classed or plain)."""
    text = fragment or ""
    marks = list(_PAGE_MARK_RE.finditer(text))
    if not marks:
        return [(1, text.strip())] if text.strip() else []
    pages: list[tuple[int, str]] = []
    for idx, match in enumerate(marks):
        start = match.end()
        end = marks[idx + 1].start() if idx + 1 < len(marks) else len(text)
        pages.append((int(match.group(1)), text[start:end].strip()))
    return pages


def join_ocr_html_pages(pages: list[tuple[int, str]]) -> str:
    parts: list[str] = []
    for i, (num, body) in enumerate(pages):
        if i:
            parts.append("<hr>")
        parts.append(f'<p class="page-label">Page {num}</p>')
        if body:
            parts.append(body)
    return "\n".join(parts)


def render_pdf_page_image(pdf_path: str | Path, page_index: int, dpi: int = 200):
    """Return a PIL image for 0-based *page_index*, or None."""
    path = Path(pdf_path)
    if not path.is_file():
        return None
    first = page_index + 1
    try:
        from pdf2image import convert_from_path

        images = convert_from_path(
            str(path), dpi=dpi, first_page=first, last_page=first
        )
        if images:
            return images[0]
    except Exception:
        pass
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        if page_index < 0 or page_index >= len(pdf):
            return None
        return pdf[page_index].render(scale=dpi / 72).to_pil()
    except Exception:
        pass
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "page"
            try:
                subprocess.run(
                    [
                        "pdftoppm",
                        "-png",
                        "-r",
                        str(int(dpi)),
                        "-f",
                        str(first),
                        "-l",
                        str(first),
                        str(path),
                        str(prefix),
                    ],
                    check=True,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, OSError):
                return None
            pngs = sorted(Path(tmp).glob("page*.png"))
            if not pngs:
                return None
            try:
                from PIL import Image

                return Image.open(pngs[0]).copy()
            except Exception:
                return None
    return None


def _tesseract_image(image, psm: int = 6) -> str:
    if image is None or not shutil.which("tesseract"):
        return ""
    from PIL import Image

    if not isinstance(image, Image.Image):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "page.png"
        image.save(img_path)
        out_base = Path(tmp) / "out"
        try:
            subprocess.run(
                [
                    "tesseract",
                    str(img_path),
                    str(out_base),
                    "-l",
                    "gle+eng",
                    "--psm",
                    str(psm),
                ],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, OSError):
            try:
                subprocess.run(
                    [
                        "tesseract",
                        str(img_path),
                        str(out_base),
                        "-l",
                        "eng",
                        "--psm",
                        str(psm),
                    ],
                    check=True,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, OSError):
                return ""
        txt = Path(str(out_base) + ".txt")
        if not txt.exists():
            return ""
        return txt.read_text(encoding="utf-8", errors="replace")


def ocr_page_image_columns(image) -> list[str]:
    """OCR a two-column bulletin page. Crop the stitcher strip, then columns."""
    if image is None:
        return []
    width, height = image.size
    top = int(height * 0.035)
    body = image.crop((0, top, width, height))
    mid = body.size[0] // 2
    overlap = max(12, body.size[0] // 80)
    left = body.crop((0, 0, mid + overlap, body.size[1]))
    right = body.crop((mid - overlap, 0, body.size[0], body.size[1]))
    left_text = _tesseract_image(left, psm=6)
    right_text = _tesseract_image(right, psm=6)
    combined = (left_text or "").rstrip() + "\n\n" + (right_text or "").rstrip()
    lines = [ln.rstrip() for ln in combined.splitlines()]
    # Drop leftover stitcher URL crumbs from the cropped strip.
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if re.search(r"https?://\S*parishpress", stripped, re.I):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return cleaned


def ocr_pdf_page_lines(pdf_path: str | Path, page_index: int) -> list[str]:
    image = render_pdf_page_image(pdf_path, page_index)
    return ocr_page_image_columns(image)


def fill_sparse_ocr_pages(
    pdf_path: str | Path,
    pages_text: list[list[str]],
) -> list[list[str]]:
    """Replace banner-only page line lists with image OCR when it finds more text."""
    filled = [list(lines or []) for lines in pages_text]
    for idx, lines in enumerate(filled):
        if not page_is_sparse(lines):
            continue
        replacement = ocr_pdf_page_lines(pdf_path, idx)
        if (
            ocr_lines_look_usable(replacement)
            and page_text_char_count(replacement) > page_text_char_count(lines)
        ):
            filled[idx] = replacement
            print(
                f"  Filled sparse mega page {idx + 1} "
                f"({page_text_char_count(lines)} -> {page_text_char_count(replacement)} chars)."
            )
    return filled


def fill_sparse_pages_in_ocr_html(
    fragment: str,
    pdf_path: str | Path,
    *,
    only_pages: set[int] | None = None,
) -> str:
    """Replace sparse page bodies in existing OCR HTML; keep rich pages intact."""
    from ocr.convert_bulletin import render_markdown_lines

    pages = split_ocr_html_pages(fragment)
    if not pages:
        return fragment or ""
    out: list[tuple[int, str]] = []
    for num, body in pages:
        if only_pages is not None and num not in only_pages:
            out.append((num, body))
            continue
        if not page_html_is_sparse(body):
            out.append((num, body))
            continue
        lines = ocr_pdf_page_lines(pdf_path, num - 1)
        if not ocr_lines_look_usable(lines):
            out.append((num, body))
            continue
        if page_text_char_count(lines) <= page_text_char_count(_plain(body).splitlines()):
            out.append((num, body))
            continue
        rendered = "\n".join(render_markdown_lines(lines))
        out.append((num, rendered))
        print(f"  Filled sparse mega-OCR HTML page {num}.")
    return join_ocr_html_pages(out)


def prefer_embedded_pages_in_ocr_html(fragment: str, pdf_path: str | Path) -> str:
    """Replace OCR HTML page bodies with native PDF text when it is not sparse.

    Image / banner-only pages are left untouched so vision or fill_sparse
    can still cover them.
    """
    from ocr.convert_bulletin import render_markdown_lines
    from ocr.text_extract import extract_all_page_lines

    pages = split_ocr_html_pages(fragment)
    if not pages:
        return fragment or ""
    native = extract_all_page_lines(pdf_path) or []
    out: list[tuple[int, str]] = []
    preferred = 0
    for num, body in pages:
        idx = num - 1
        native_lines = native[idx] if 0 <= idx < len(native) else None
        if native_lines and not page_is_sparse(native_lines):
            rendered = "\n".join(render_markdown_lines(native_lines))
            out.append((num, rendered))
            preferred += 1
        else:
            out.append((num, body))
    print(f"Preferred embedded PDF text on {preferred} page(s).")
    return join_ocr_html_pages(out)
