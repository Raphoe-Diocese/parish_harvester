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
import statistics
import subprocess
import tempfile
from pathlib import Path

from ocr.text_extract import (
    extract_all_page_lines,
    page_is_sparse,
    page_text_char_count,
)

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
_BROKEN_ORDINAL_RE = re.compile(r"\d+[™“”*]+|[™“”][A-Za-z]")
_SMASH_FRAG_RE = re.compile(
    r"gi\s+Teach|Réalt\s+n\b|thth|\bAn\s+thth\b",
    re.IGNORECASE,
)


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


def ocr_lines_look_smashed(lines: list[str] | None) -> bool:
    """True when vision read across columns (Annagry / Dunfanaghy style)."""
    text = "\n".join(lines or []).strip()
    if len(text) < 80:
        return False
    tokens = _SINGLE_TOKEN_RE.findall(text)
    words = [
        tok
        for tok in tokens
        if "@" not in tok
        and "http" not in tok.lower()
        and not tok.lower().startswith("www.")
    ]
    if len(words) < 20:
        return False
    if _SMASH_FRAG_RE.search(text):
        return True
    if text.count("|") >= 4:
        return True
    if len(_BROKEN_ORDINAL_RE.findall(text)) >= 3:
        return True
    short = sum(1 for tok in words if len(tok) <= 2)
    singles = sum(1 for tok in words if len(tok) == 1 and tok.isalpha())
    avg = sum(len(tok) for tok in words) / len(words)
    if short / len(words) >= 0.38 and avg < 3.6:
        return True
    if singles / len(words) >= 0.16 and short / len(words) >= 0.30:
        return True
    return False


def column_smash_score(lines: list[str] | None) -> float:
    """How much *lines* read like two columns glued together — lower is better.

    :func:`ocr_lines_look_smashed` is a yes/no gate tuned to catch bad OCR,
    so it also fires on clean column reads that keep printed superscript
    ordinals (``22™Aug``). Comparing scores lets a repair be accepted when
    it is genuinely better than what is on the page today.
    """
    text = "\n".join(lines or []).strip()
    if not text:
        return 0.0
    tokens = _SINGLE_TOKEN_RE.findall(text)
    words = [
        tok
        for tok in tokens
        if "@" not in tok
        and "http" not in tok.lower()
        and not tok.lower().startswith("www.")
    ]
    if not words:
        return 0.0
    short = sum(1 for tok in words if len(tok) <= 2) / len(words)
    singles = sum(1 for tok in words if len(tok) == 1 and tok.isalpha()) / len(words)
    pipes = text.count("|") / max(1.0, len(text) / 1000.0)
    score = short + 2.0 * singles + 0.05 * pipes
    if _SMASH_FRAG_RE.search(text):
        score += 1.0
    return round(score, 4)


def replacement_is_better(
    replacement: list[str] | None,
    current: list[str] | None,
) -> bool:
    """True when re-reading a page by column beat the text already there."""
    if not ocr_lines_look_usable(replacement):
        return False
    if not ocr_lines_look_smashed(replacement):
        return True
    return column_smash_score(replacement) < column_smash_score(current) - 0.05


def page_ocr_needs_image_repair(
    vision_lines: list[str] | None,
    embedded_lines: list[str] | None,
) -> bool:
    """Image/banner pages whose current OCR is empty or column-smashed."""
    if embedded_lines and not page_is_sparse(embedded_lines):
        return False
    if page_is_sparse(vision_lines):
        return True
    return ocr_lines_look_smashed(vision_lines)


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
        import pymupdf
        from PIL import Image

        doc = pymupdf.open(str(path))
        try:
            if page_index < 0 or page_index >= doc.page_count:
                return None
            pix = doc[page_index].get_pixmap(dpi=dpi)
            mode = "RGBA" if pix.alpha else "RGB"
            return Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        finally:
            doc.close()
    except Exception:
        pass
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


def column_rule_xs(image) -> list[int]:
    """Return x positions of printed vertical column rules.

    Many parish bulletins separate a narrow contacts sidebar from the main
    column with a drawn line instead of white space. That line is *ink*, so
    the empty-valley scan in :func:`column_gutter_xs` sees a peak exactly
    where the gutter is and reports one column. A rule is recognised by a
    single near-full-height run of dark pixels: body text never produces one.
    """
    if image is None:
        return []
    gray = image.convert("L")
    width, height = gray.size
    if width < 80 or height < 80:
        return []
    pixels = gray.load()
    y0 = int(height * 0.08)
    span = height - y0
    if span < 40:
        return []
    min_run = int(span * 0.6)
    left_edge, right_edge = int(width * 0.12), int(width * 0.88)
    runs: list[tuple[int, int]] = []
    for x in range(left_edge, right_edge):
        best = run = 0
        for y in range(y0, height):
            if pixels[x, y] < 200:
                run += 1
                if run > best:
                    best = run
            else:
                run = 0
        if best >= min_run:
            runs.append((x, best))
    if not runs:
        return []
    # A rule is 1–3px wide; keep one x per group of adjacent hits.
    groups: list[list[tuple[int, int]]] = [[runs[0]]]
    for item in runs[1:]:
        if item[0] - groups[-1][-1][0] <= max(3, width // 200):
            groups[-1].append(item)
        else:
            groups.append([item])
    min_col = int(width * 0.18)
    gutters: list[int] = []
    prev = 0
    for group in groups:
        x = max(group, key=lambda item: item[1])[0]
        if x - prev >= min_col and width - x >= min_col:
            gutters.append(x)
            prev = x
    return gutters[:2]


def column_gutter_xs(image) -> list[int]:
    """Return x positions of vertical column gutters, or [] for one column.

    Annagry is a narrow left sidebar (~30%) plus a wide right column — a
    50/50 split cuts through the main text. Only split on a real boundary:
    a drawn column rule, else an empty ink valley.
    """
    if image is None:
        return []
    ruled = column_rule_xs(image)
    if ruled:
        return ruled
    gray = image.convert("L")
    width, height = gray.size
    if width < 80 or height < 80:
        return []
    pixels = gray.load()
    y0 = int(height * 0.08)
    ink = []
    for x in range(width):
        dark = 0
        for y in range(y0, height):
            if pixels[x, y] < 200:
                dark += 1
        ink.append(dark)
    radius = max(3, width // 120)
    smooth = []
    for idx in range(width):
        window = ink[max(0, idx - radius) : idx + radius + 1]
        smooth.append(sum(window) / len(window))
    median = statistics.median(smooth) if smooth else 0
    if median < 8:
        return []
    threshold = max(20.0, median * 0.28)
    neighbourhood = max(8, width // 40)
    left_edge = int(width * 0.12)
    right_edge = int(width * 0.88)
    raw: list[int] = []
    for x in range(left_edge, right_edge):
        nearby = smooth[max(0, x - neighbourhood) : x + neighbourhood + 1]
        if smooth[x] <= min(nearby) and smooth[x] < threshold:
            if raw and x - raw[-1] < int(width * 0.12):
                if smooth[x] < smooth[raw[-1]]:
                    raw[-1] = x
            else:
                raw.append(x)
    min_col = int(width * 0.18)
    gutters: list[int] = []
    prev = 0
    for x in raw:
        if x - prev >= min_col and width - x >= min_col:
            gutters.append(x)
            prev = x
    return gutters[:2]


def _column_strips(image, gutters: list[int]):
    """Crop one image per column, insetting past the boundary.

    Overlapping the strips dragged the neighbouring column's first glyphs
    (and any printed rule) into both reads, which is what produced the
    ``t|`` / ``»|`` line prefixes. Only the outer page edges are kept whole.
    """
    width, height = image.size
    inset = max(4, width // 150)
    edges = [0, *gutters, width]
    strips = []
    last = len(edges) - 1
    for idx in range(last):
        x0 = max(0, edges[idx] + (inset if idx else 0))
        x1 = min(width, edges[idx + 1] - (inset if idx < last - 1 else 0))
        if x1 - x0 < 20:
            continue
        strips.append(image.crop((x0, 0, x1, height)))
    return strips or [image]


_WORDISH_RE = re.compile(r"[^\W_]{3,}", re.UNICODE)


def _is_scan_speckle(line: str) -> bool:
    """True for short OCR crumbs off decorative artwork (``al 4``, ``| I '``).

    Deliberately narrow: only short lines with no three-character run of
    letters or digits anywhere. Real short notices (``10.00am``, ``€1,920``,
    ``No Mass``) all keep such a run, so nothing readable is dropped.
    """
    text = (line or "").strip()
    if not text or len(text) > 12:
        return False
    return not _WORDISH_RE.search(text)


def ocr_page_image_columns(image) -> list[str]:
    """OCR a bulletin page left-to-right by detected columns, then top-to-bottom."""
    if image is None:
        return []
    width, height = image.size
    top = int(height * 0.035)
    body = image.crop((0, top, width, height))
    strips = _column_strips(body, column_gutter_xs(body))
    texts = [_tesseract_image(strip, psm=6) for strip in strips]
    combined = "\n\n".join((text or "").rstrip() for text in texts)
    lines = [ln.rstrip() for ln in combined.splitlines()]
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if re.search(r"https?://\S*parishpress", stripped, re.I):
            continue
        if _is_scan_speckle(stripped):
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


def repair_image_page_ocr(
    pdf_path: str | Path,
    pages_text: list[list[str]] | None,
) -> list[list[str]] | None:
    """Replace smashed/empty image-page OCR with column tesseract when usable."""
    if not pages_text:
        return pages_text
    embedded = extract_all_page_lines(pdf_path) or []
    filled = [list(lines or []) for lines in pages_text]
    for idx, lines in enumerate(filled):
        native = embedded[idx] if idx < len(embedded) else []
        if not page_ocr_needs_image_repair(lines, native):
            continue
        replacement = ocr_pdf_page_lines(pdf_path, idx)
        if not replacement_is_better(replacement, lines):
            continue
        filled[idx] = replacement
        print(
            f"  Repaired image mega page {idx + 1} "
            f"({page_text_char_count(lines)} -> {page_text_char_count(replacement)} chars)."
        )
    return filled


def repair_image_pages_in_ocr_html(fragment: str, pdf_path: str | Path) -> str:
    """Replace smashed image-page bodies in existing OCR HTML."""
    from ocr.convert_bulletin import render_markdown_lines

    pages = split_ocr_html_pages(fragment)
    if not pages:
        return fragment or ""
    embedded = extract_all_page_lines(pdf_path) or []
    out: list[tuple[int, str]] = []
    for num, body in pages:
        vision_lines = _plain(body).splitlines()
        native = embedded[num - 1] if 0 <= num - 1 < len(embedded) else []
        if not page_ocr_needs_image_repair(vision_lines, native):
            out.append((num, body))
            continue
        lines = ocr_pdf_page_lines(pdf_path, num - 1)
        if not replacement_is_better(lines, vision_lines):
            out.append((num, body))
            continue
        rendered = "\n".join(render_markdown_lines(lines))
        out.append((num, rendered))
        print(f"  Repaired smashed mega-OCR HTML page {num}.")
    return join_ocr_html_pages(out)


def polish_ocr_html_from_pdf(fragment: str, pdf_path: str | Path) -> str:
    """Born-digital pages keep PDF text; smashed image pages get column OCR."""
    polished = prefer_embedded_pages_in_ocr_html(fragment, pdf_path)
    return repair_image_pages_in_ocr_html(polished, pdf_path)
