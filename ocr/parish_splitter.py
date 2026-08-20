from __future__ import annotations

"""Split diocese mega-bulletin OCR text into per-parish chunks."""

import html as _html_utils
import re
from typing import Iterable, NamedTuple


def _name_patterns(display_name: str) -> tuple[list[str], list[str]]:
    """Return (strong_patterns, weak_patterns) for a parish display name.

    Strong patterns may stand alone as title lines (e.g. ``X Parish``,
    ``Parish of X``). Weak patterns are short bare names that only count when
    the next line is a newsletter URL (stitcher banner).
    """
    name = (display_name or "").strip()
    if not name:
        return [], []
    strong: list[str] = []
    weak: list[str] = []
    if name.lower().endswith(" parish"):
        strong.append(name)
        short = name[:-7].strip()
        if short:
            weak.append(short)
    else:
        strong.append(f"{name} Parish")
        # Long bare titles can stand alone; short ones need a URL banner line.
        if len(name) >= 8:
            strong.append(name)
        else:
            weak.append(name)
    short = re.sub(r"\s*\(.*\)\s*", "", name).strip()
    if short and short.lower() != name.lower():
        if short.lower().endswith(" parish") or len(short) >= 8:
            strong.append(short)
        else:
            weak.append(short)
            strong.append(f"{short} Parish")
    strong = sorted({p for p in strong if len(p) >= 3}, key=len, reverse=True)
    weak = sorted(
        {p for p in weak if len(p) >= 3 and p.lower() not in {s.lower() for s in strong}},
        key=len,
        reverse=True,
    )
    return strong, weak


def _cleaned_title(line: str) -> str:
    cleaned = (line or "").strip()
    cleaned = cleaned.rstrip(".,:;!")
    return re.sub(r"\s+", " ", cleaned).strip()


_INLINE_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _line_matches_patterns(cleaned: str, patterns: list[str]) -> bool:
    if not cleaned or len(cleaned) > 80:
        return False
    lower = cleaned.lower()
    for pattern in patterns:
        p = pattern.lower()
        if lower == p:
            return True
        if lower == f"parish of {p}":
            return True
        if lower == f"the parish of {p}":
            return True
        if lower == f"{p} parish":
            return True
        if lower == f"{p} parish newsletter":
            return True
        if lower == f"{p} newsletter":
            return True
    return False


def _strip_inline_url(cleaned: str) -> str:
    return _cleaned_title(_INLINE_URL_RE.sub("", cleaned or ""))


def _line_matches_banner(
    cleaned: str,
    patterns: list[str],
    *,
    next_is_url: bool,
    self_has_url: bool,
) -> bool:
    """Match a stitcher banner line from real mega-OCR HTML.

    Live convert_bulletin output often puts ``Name`` and the newsletter URL
    in the *same* ``<p>`` (newline, no ``<br>``), or glues the name onto the
    last body words of the first page (``Recent DeathsArdara`` + URL). Exact
    standalone titles still match; URL-adjacent suffix matches cover the
    glued-banner case without treating every body mention as a marker.
    """
    if _line_matches_patterns(cleaned, patterns):
        return True
    name_part = _strip_inline_url(cleaned) if self_has_url else cleaned
    if self_has_url and _line_matches_patterns(name_part, patterns):
        return True
    if not (self_has_url or next_is_url):
        return False
    lower = (name_part or "").lower()
    if not lower:
        return False
    for pattern in patterns:
        p = pattern.lower()
        if len(p) < 4:
            continue
        if lower == p or lower.endswith(p):
            return True
    return False


def _line_is_parish_marker(line: str, patterns: list[str]) -> bool:
    """Compatibility helper: true if line matches any of the given patterns."""
    return _line_matches_patterns(_cleaned_title(line), patterns)


def _next_line_is_url(next_line: str) -> bool:
    nxt = (next_line or "").strip().lower()
    if nxt.startswith("http://") or nxt.startswith("https://") or nxt.startswith("www."):
        return True
    plain = re.sub(r"<[^>]+>", " ", nxt)
    plain = _html_utils.unescape(plain).strip().lower()
    return plain.startswith("http://") or plain.startswith("https://") or plain.startswith("www.")


def split_ocr_by_parish(
    ocr_text: str,
    parish_entries: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Map ``parish_key`` → OCR chunk for that parish.

    Finds parish display names as standalone title lines in the mega bulletin
    OCR (including stitcher banners OCR'd as ``Name`` then URL) and slices
    text between consecutive markers.
    """
    text = (ocr_text or "").strip()
    entries = list(parish_entries)
    if not text:
        return {key: "" for key, _ in entries}

    pattern_map: dict[str, tuple[list[str], list[str]]] = {
        key: _name_patterns(display_name) for key, display_name in entries
    }

    markers: list[tuple[int, str]] = []
    lines = text.splitlines(keepends=True)
    # Precompute next non-empty stripped line for each index
    stripped_lines = [ln.strip() for ln in lines]
    next_nonempty: list[str] = [""] * len(lines)
    upcoming = ""
    for i in range(len(lines) - 1, -1, -1):
        next_nonempty[i] = upcoming
        if stripped_lines[i]:
            upcoming = stripped_lines[i]

    offset = 0
    for i, line in enumerate(lines):
        raw_stripped = line.strip()
        cleaned = _cleaned_title(line)
        # "Rathmullan: 087…" body lines — colon titles only count with a URL next.
        if raw_stripped.endswith(":") and not _next_line_is_url(next_nonempty[i]):
            offset += len(line)
            continue
        if cleaned:
            self_has_url = bool(_INLINE_URL_RE.search(raw_stripped))
            nxt_url = _next_line_is_url(next_nonempty[i])
            for key, (strong, weak) in pattern_map.items():
                if _line_matches_banner(
                    cleaned, strong, next_is_url=nxt_url, self_has_url=self_has_url
                ) or (
                    (nxt_url or self_has_url)
                    and _line_matches_banner(
                        cleaned, weak, next_is_url=nxt_url, self_has_url=self_has_url
                    )
                ):
                    markers.append((offset, key))
                    break
        offset += len(line)

    if not markers:
        return {key: "" for key, _ in entries}

    earliest: dict[str, int] = {}
    for pos, key in markers:
        if key not in earliest or pos < earliest[key]:
            earliest[key] = pos

    ordered = sorted(earliest.items(), key=lambda item: item[1])
    chunks: dict[str, str] = {key: "" for key, _ in entries}

    for idx, (key, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(text)
        chunks[key] = text[start:end].strip()

    return chunks


class ParishPageChunk(NamedTuple):
    """One parish's slice of a diocese's OCR HTML, plus the mega-PDF page
    range it came from (1-indexed, inclusive) — ``None`` when no name-marker
    for that parish could be found anywhere in the OCR text this week."""

    html: str
    start_page: int | None
    end_page: int | None


_PAGE_LABEL_RE = re.compile(
    r'<p\s+class="page-label"[^>]*>\s*Page\s+(\d+)\s*</p>', re.IGNORECASE
)
_HTML_BLOCK_RE = re.compile(
    r'(?P<heading><h[1-6]\b[^>]*>.*?</h[1-6]>)'
    r'|(?P<hr><hr\s*/?>)'
    r'|(?P<table><table\b[\s\S]*?</table>)'
    r'|(?P<classed_p><p\s+class="[^"]*"[^>]*>.*?</p>)'
    r'|(?P<plain_p><p\b[^>]*>.*?</p>)',
    re.IGNORECASE | re.DOTALL,
)
_STRIP_P_WRAPPER_RE = re.compile(r'^<p\b[^>]*>|</p>\s*$', re.IGNORECASE | re.DOTALL)


def _block_plain_text(html_fragment: str) -> str:
    text = html_fragment or ""
    for _ in range(4):
        text = _html_utils.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_br_lines(inner_html: str) -> list[str]:
    """Split a ``<p>`` inner HTML into original OCR lines.

    ``convert_bulletin`` joins lines with ``<br>``. After
    ``tighten_ocr_paragraphs`` re-renders inline markup, the live diocese
    pages often keep a raw newline between the stitcher name and the
    newsletter ``<a href>`` instead of a ``<br>``. Treat both as line breaks
    so name-marker matching can see the banner.
    """
    chunks = re.split(r"(?:<br\s*/?>)|(?:\n+)", inner_html or "")
    return [seg.strip() for seg in chunks if seg.strip()]


def _tokenize_ocr_units(fragment: str) -> list[tuple[str, str]]:
    """Tokenize a *raw* (pre-``tighten_ocr_paragraphs``) OCR HTML fragment
    into ``(kind, html)`` units.

    ``ocr.convert_bulletin.render_markdown_lines`` already joins consecutive
    OCR lines into one ``<p>…<br>…</p>`` per paragraph, which is coarser than
    the single-line granularity :func:`split_ocr_by_parish` needs to find a
    parish's name-marker line. This explodes plain (unclassed) ``<p>`` tags
    back into one unit per original ``<br>``-joined line while keeping
    headings, ``<hr>``, tables and the per-page ``<p class="page-label">``
    markers as whole units.
    """
    units: list[tuple[str, str]] = []
    pos = 0
    for match in _HTML_BLOCK_RE.finditer(fragment):
        if match.start() > pos:
            gap = fragment[pos:match.start()].strip()
            if gap:
                units.append(("line", gap))
        if match.group("heading"):
            units.append(("block", match.group("heading")))
        elif match.group("hr"):
            units.append(("block", match.group("hr")))
        elif match.group("table"):
            units.append(("block", match.group("table")))
        elif match.group("classed_p"):
            whole = match.group("classed_p")
            if _PAGE_LABEL_RE.match(whole.strip()):
                units.append(("page", whole))
            else:
                units.append(("block", whole))
        elif match.group("plain_p"):
            inner = _STRIP_P_WRAPPER_RE.sub("", match.group("plain_p")).strip()
            for line in _split_br_lines(inner):
                units.append(("line", line))
        pos = match.end()
    tail = fragment[pos:].strip()
    if tail:
        units.append(("line", tail))
    return units


def split_ocr_html_by_parish(
    raw_ocr_fragment: str,
    parish_entries: Iterable[tuple[str, str]],
) -> dict[str, ParishPageChunk]:
    """Slice a diocese's OCR HTML into per-parish chunks *and* report the
    mega-PDF page range each chunk spans — without re-running OCR.

    Reuses the exact "OCR once, reuse everywhere" output already produced
    for the diocese viewer page. Every mega-PDF page carries its own
    ``<p class="page-label">Page N</p>`` marker (see
    :func:`ocr.convert_bulletin.build_html_content`), and
    :func:`harvester.stitcher.stitch_mega_pdf` only ever appends *whole*
    pages per parish — so page-label positions give an exact, page-aligned
    boundary once a parish's first name-marker line is found (same matching
    rules as :func:`split_ocr_by_parish`, just applied at HTML-line
    granularity instead of flattened plain text).

    *raw_ocr_fragment* should be the fragment **before**
    :func:`ocr.generate_bulletin_pages.tighten_ocr_paragraphs` regroups
    paragraphs, so each original OCR line can still be told apart. Each
    parish's sliced sub-fragment is re-tightened before being returned, so
    it reads with the same paragraph-merged polish as the main diocese OCR
    panel.
    """
    from ocr.generate_bulletin_pages import tighten_ocr_paragraphs

    entries = list(parish_entries)
    empty = {key: ParishPageChunk(html="", start_page=None, end_page=None) for key, _ in entries}
    fragment = (raw_ocr_fragment or "").strip()
    if not fragment or not entries:
        return empty

    tokens = _tokenize_ocr_units(fragment)
    if not tokens:
        return empty

    plain_texts = [
        "" if kind == "page" else _block_plain_text(content) for kind, content in tokens
    ]
    next_nonempty: list[str] = [""] * len(tokens)
    upcoming = ""
    for i in range(len(tokens) - 1, -1, -1):
        next_nonempty[i] = upcoming
        if plain_texts[i]:
            upcoming = plain_texts[i]

    pattern_map = {key: _name_patterns(name) for key, name in entries}
    page_at: list[int | None] = [None] * len(tokens)
    current_page = 1
    markers: list[tuple[int, str]] = []
    for i, (kind, content) in enumerate(tokens):
        if kind == "page":
            page_match = _PAGE_LABEL_RE.match(content.strip())
            if page_match:
                current_page = int(page_match.group(1))
        page_at[i] = current_page
        if kind == "page":
            continue
        # Body-text lines are the expected shape (the stitcher's per-parish
        # banner overlay renders as plain OCR'd text) but headings are
        # checked too — some OCR passes render a bold banner as a heading,
        # and flattened legacy accordion markup uses <h2 class="b-title">.
        cleaned = _cleaned_title(plain_texts[i])
        if not cleaned:
            continue
        nxt_url = _next_line_is_url(next_nonempty[i])
        if cleaned.endswith(":") and not nxt_url:
            continue
        self_has_url = bool(_INLINE_URL_RE.search(plain_texts[i]))
        for key, (strong, weak) in pattern_map.items():
            if _line_matches_banner(
                cleaned, strong, next_is_url=nxt_url, self_has_url=self_has_url
            ) or (
                (nxt_url or self_has_url)
                and _line_matches_banner(
                    cleaned, weak, next_is_url=nxt_url, self_has_url=self_has_url
                )
            ):
                markers.append((i, key))
                break

    if not markers:
        return empty

    earliest: dict[str, int] = {}
    for idx, key in markers:
        if key not in earliest or idx < earliest[key]:
            earliest[key] = idx

    def _extend_start_backward(idx: int) -> int:
        """Start a parish at the beginning of the mega-PDF page that holds
        its first banner, not at the banner line itself.

        The 9pt stitcher overlay is often OCR'd mid-page (glued onto
        ``Recent DeathsArdara`` after other first-page lines). Walking back
        only over a leading ``<hr>`` + page-label left those earlier lines
        stuck on the previous parish and leaked the next parish's first
        page into the PDF slice.
        """
        marker_page = page_at[idx]
        j = idx
        while j > 0 and page_at[j - 1] == marker_page:
            j -= 1
        while j > 0 and (
            tokens[j - 1][0] == "page"
            or (tokens[j - 1][0] == "block" and tokens[j - 1][1].strip().lower().startswith("<hr"))
        ):
            j -= 1
        return j

    def _first_page_in_range(start: int, end: int) -> int | None:
        """The page-label value inside ``[start, end)`` (the boundary
        extension always pulls a parish's own leading label into its
        range), falling back to whatever page was already open at
        ``start`` if this parish had no page-label of its own."""
        for i in range(start, end):
            if tokens[i][0] == "page":
                return page_at[i]
        return page_at[start] if start < len(tokens) else None

    ordered = sorted(earliest.items(), key=lambda item: item[1])
    start_indices = [_extend_start_backward(marker_idx) for _key, marker_idx in ordered]
    chunks: dict[str, ParishPageChunk] = dict(empty)
    for pos, (key, _marker_idx) in enumerate(ordered):
        start_idx = start_indices[pos]
        end_idx = start_indices[pos + 1] if pos + 1 < len(ordered) else len(tokens)
        pieces: list[str] = []
        for kind, content in tokens[start_idx:end_idx]:
            pieces.append(f"<p>{content}</p>" if kind == "line" else content)
        raw_chunk_html = "\n".join(pieces)
        chunk_html = tighten_ocr_paragraphs(raw_chunk_html).strip()
        start_page = _first_page_in_range(start_idx, end_idx)
        end_page = page_at[end_idx - 1] if end_idx > start_idx else start_page
        chunks[key] = ParishPageChunk(html=chunk_html, start_page=start_page, end_page=end_page)
    return chunks


def split_ocr_html_by_page_ranges(
    raw_ocr_fragment: str,
    page_ranges: dict[str, tuple[int, int]],
) -> dict[str, ParishPageChunk]:
    """Slice OCR HTML using authoritative 1-indexed inclusive page ranges.

    Used when the stitcher wrote ``*.pages.json`` next to the mega PDF so
    parish boundaries do not depend on OCR reading the 9pt banner.
    """
    from ocr.generate_bulletin_pages import tighten_ocr_paragraphs

    ranges = {str(key): (int(start), int(end)) for key, (start, end) in page_ranges.items()}
    empty = {
        key: ParishPageChunk(html="", start_page=None, end_page=None) for key in ranges
    }
    fragment = (raw_ocr_fragment or "").strip()
    if not fragment or not ranges:
        return empty

    tokens = _tokenize_ocr_units(fragment)
    if not tokens:
        return empty

    current_page = 1
    page_at: list[int] = []
    for kind, content in tokens:
        if kind == "page":
            page_match = _PAGE_LABEL_RE.match(content.strip())
            if page_match:
                current_page = int(page_match.group(1))
        page_at.append(current_page)

    chunks: dict[str, ParishPageChunk] = dict(empty)
    for key, (start_page, end_page) in ranges.items():
        if end_page < start_page:
            continue
        pieces: list[str] = []
        first = last = None
        for (kind, content), page in zip(tokens, page_at):
            if page < start_page or page > end_page:
                continue
            pieces.append(f"<p>{content}</p>" if kind == "line" else content)
            first = page if first is None else first
            last = page
        if not pieces:
            continue
        raw_chunk_html = "\n".join(pieces)
        chunk_html = tighten_ocr_paragraphs(raw_chunk_html).strip()
        chunks[key] = ParishPageChunk(html=chunk_html, start_page=first, end_page=last)
    return chunks
