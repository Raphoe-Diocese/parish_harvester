"""Turn mega-OCR dumps into a readable parish bulletin.

Promote topic lines that already exist in the text to real headings, and
insert a visible parish masthead so the reader knows whose bulletin this is.
Never invent events, names, or times. Never translate Irish/Gaeilge.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

from ocr.parish_splitter import (
    _cleaned_title,
    _line_matches_banner,
    _name_patterns,
    _next_line_is_url,
)

# Topic lines we may promote — only when the words are already on the page.
_HEADING_START = re.compile(
    r"^(?:"
    r"mass\s+times(?:\s+and\s+intentions?)?(?:\s+for\s+the\s+week)?"
    r"(?:\s*/\s*anniversar\w*)?(?:\s*/\s*intentions?)?"
    r"(?:\s+in\b[^.!?]{0,60})?"
    r"|sunday\s+mass(?:es)?"
    r"|weekday\s+mass(?:es)?"
    r"|daily\s+mass(?:es)?"
    r"|mass\s+(?:and\s+confessions?\s+)?schedule"
    r"|upcoming\s+mass\s+schedule"
    r"|amanna\s+(?:an\s+)?aifrinn"
    r"|anniversar(?:y|ies)(?:\s*/\s*intentions?)?"
    r"|recent(?:ly)?\s+(?:deceased|dead|deaths?)"
    r"|rest\s+in\s+peace"
    r"|requiesca[nt]t?\s+in\s+pace"
    r"|faithful\s+departed"
    r"|month'?s?\s+mind"
    r"|we\s+pray\s+for\s+(?:the\s+)?(?:dead|deceased|faithful\s+departed)"
    r"|please\s+pray\s+for(?:\s+the\s+(?:dead|deceased|faithful\s+departed))?"
    r"|in\s+memoriam"
    r"|parish\s+notices?"
    r"|community\s+notices?"
    r"|this\s+week(?:'s)?\s+notices?"
    r"|notices?\s+for\s+(?:the\s+)?(?:week|newsletter)"
    r"|parish\s+news(?!letter\b)"
    r"|community\s+news"
    r"|fundraising"
    r"|parish\s+events?"
    r"|upcoming\s+events?"
    r"|bingo(?:\s+night)?"
    r"|parish\s+(?:contacts?|finances?)"
    r"|parish\s+office"
    r"|useful\s+numbers"
    r"|parochial\s+house(?:\s+tel(?:ephone)?\.?(?:\s+no\.?s?)?)?"
    r"|contacts?(?:\s+us)?"
    r")",
    re.IGNORECASE,
)

# Irish prayer used as a short section label only (not the full sentence).
_IRISH_RIP_HEADING = re.compile(
    r"^ar\s+dheis\s+d[eé](?:\s+go\s+raibh(?:\s+a\s+(?:anam|n-anamacha))?)?\.?$",
    re.IGNORECASE,
)

_BODY_AFTER_HEADING = re.compile(
    r"^(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?|"
    r"vigil|"
    r"\d{1,2}(?:st|nd|rd|th)?\b|"
    r"january|february|march|april|june|july|august|september|october|november|december|"
    r"fr\.?\s|rev\.?\s|"
    r"please\s+keep)",
    re.IGNORECASE,
)

_URL_ONLY = re.compile(
    r"^(?:https?://|www\.)\S+$",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(
    r"(<header\b[^>]*class=\"[^\"]*ocr-parish-masthead[\s\S]*?</header>)"
    r"|(<details\b[\s\S]*?</details>)"
    r"|(<h[1-6]\b[^>]*>.*?</h[1-6]>)"
    r"|(<p\b[^>]*>.*?</p>)"
    r"|(<hr\s*/?>)"
    r"|(<table\b[\s\S]*?</table>)"
    r"|(<div\b[^>]*ocr-failed-banner[\s\S]*?</div>)",
    re.IGNORECASE | re.DOTALL,
)

_HEADING_TAG_RE = re.compile(
    r"<h([1-6])\b([^>]*)>(.*?)</h[1-6]>",
    re.IGNORECASE | re.DOTALL,
)

_BR_SPLIT_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def format_uk_date(iso_date: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso_date or "").strip())
    if not match:
        return str(iso_date or "").strip()
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"


def _plain(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def split_heading_prefix(plain: str) -> tuple[str | None, str]:
    """If *plain* starts with a known bulletin topic, return (heading, rest).

    Restores the original wording (including Irish). Returns ``(None, plain)``
    when the line is ordinary body text.
    """
    text = _SPACE_RE.sub(" ", (plain or "").strip())
    if not text:
        return None, ""
    if _IRISH_RIP_HEADING.match(text) and len(text) <= 56:
        return text, ""
    match = _HEADING_START.match(text)
    if not match:
        return None, text
    head = match.group(0).strip()
    rest = text[match.end() :].lstrip(" \t:/|–—-")
    if not rest or re.fullmatch(r"[.:;]*", rest):
        return text.rstrip(".:;"), ""
    # Contact / office / bingo lines that continue with a phone or sentence
    # are body text, not section titles.
    if re.match(
        r"^(?:tel\b|on\b|option\b|every\b|will\b|open\b|\d|mobile\b)",
        rest,
        re.IGNORECASE,
    ):
        return None, text
    if _BODY_AFTER_HEADING.match(rest):
        return head, rest
    if re.search(r"\d", rest) or re.search(r"\bwill\b|\bevery\b|\bplease\b", rest, re.I):
        return None, text
    if len(text) <= 80 and len(rest) <= 40:
        return text.rstrip(".:;"), ""
    return None, text


def classify_heading_line(plain: str) -> str | None:
    """Return the heading text when the whole line should become an h3."""
    head, rest = split_heading_prefix(plain)
    if head and not rest:
        return head
    return None


def render_parish_masthead(
    display_name: str,
    bulletin_date: str = "",
    *,
    website: str = "",
) -> str:
    """Visible header so the reader knows whose bulletin this is."""
    name = html.escape((display_name or "").strip() or "Parish bulletin")
    date_label = format_uk_date(bulletin_date)
    date_html = (
        f'<p class="ocr-parish-date">{html.escape(date_label)}</p>' if date_label else ""
    )
    link_html = ""
    href = (website or "").strip()
    if href.startswith(("http://", "https://")):
        safe_href = html.escape(href, quote=True)
        link_html = (
            f'<p class="ocr-parish-link"><a href="{safe_href}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(href)}</a></p>'
        )
    return (
        f'<header class="ocr-parish-masthead">'
        f'<h2 class="ocr-parish-name">{name}</h2>'
        f"{date_html}{link_html}"
        f"</header>"
    )


def _looks_like_parish_name(plain: str, entries: list[tuple[str, str, list[str], list[str]]], next_plain: str) -> tuple[str, str] | None:
    cleaned = _cleaned_title(plain)
    self_has_url = bool(_URL_ONLY.match(cleaned) or "http" in cleaned.lower() or cleaned.lower().startswith("www."))
    next_is_url = _next_line_is_url(next_plain) or _URL_ONLY.match(_plain(next_plain) or "")
    for key, display_name, strong, weak in entries:
        patterns = strong + weak
        if _line_matches_banner(
            cleaned,
            patterns,
            next_is_url=bool(next_is_url),
            self_has_url=self_has_url,
        ):
            return key, display_name
    return None


def _is_url_only_line(plain: str) -> bool:
    text = (plain or "").strip().rstrip("/")
    if not text:
        return False
    if _URL_ONLY.match(text):
        return True
    compact = text.lower().replace("https://", "").replace("http://", "")
    return bool(compact) and " " not in compact and "." in compact and len(compact) < 80


def _emit_paragraph(lines: list[str]) -> str:
    kept = [ln for ln in lines if ln.strip()]
    if not kept:
        return ""
    return "<p>" + "<br>\n".join(kept) + "</p>"


def _heading_html(text: str) -> str:
    return f'<h3 class="b-head">{html.escape(text)}</h3>'


def _reset_reader_markup(fragment: str) -> str:
    """Undo a previous structure pass so we can re-apply rules safely."""

    def _masthead_to_name(match: re.Match[str]) -> str:
        inner = match.group(0)
        name_m = re.search(r"ocr-parish-name[^>]*>(.*?)</h2>", inner, re.I | re.S)
        name = _plain(name_m.group(1)) if name_m else ""
        return f"<p>{html.escape(name)}</p>" if name else ""

    text = re.sub(
        r"<header\b[^>]*ocr-parish-masthead[\s\S]*?</header>",
        _masthead_to_name,
        fragment or "",
        flags=re.I,
    )
    text = re.sub(r'<h3 class="b-head">(.*?)</h3>', r"<p>\1</p>", text, flags=re.I | re.S)
    return text


def structure_ocr_html(
    fragment: str,
    *,
    parish_entries: Iterable[tuple[str, str]] | None = None,
    bulletin_date: str = "",
    parish_urls: dict[str, str] | None = None,
    single_parish_name: str | None = None,
) -> str:
    """Idempotent reader layout: parish mastheads + real section headings.

    Page order is preserved. No accordion / ``<details>``. Existing
    ``ocr-parish-masthead`` blocks are kept. Topic headings already marked
    ``b-head`` / ``b-title`` are left alone.
    """
    source = _reset_reader_markup(fragment or "")
    entries_raw = list(parish_entries or [])
    packed: list[tuple[str, str, list[str], list[str]]] = []
    for key, display_name in entries_raw:
        strong, weak = _name_patterns(display_name)
        packed.append((key, display_name, strong, weak))
    urls = parish_urls or {}
    seen_parish: set[str] = set()
    out: list[str] = []

    if single_parish_name and "ocr-parish-masthead" not in source:
        out.append(render_parish_masthead(single_parish_name, bulletin_date))
        seen_parish.add(single_parish_name.lower())

    def add_masthead(display_name: str, key: str = "") -> None:
        marker = display_name.lower()
        if marker in seen_parish:
            return
        seen_parish.add(marker)
        website = urls.get(key) or urls.get(display_name) or ""
        out.append(render_parish_masthead(display_name, bulletin_date, website=""))
        _ = website  # name + date only — grid/PDF already carry the URL

    def process_plain_lines(raw_lines: list[str], *, allow_parish: bool) -> None:
        body: list[str] = []

        def flush() -> None:
            nonlocal body
            chunk = _emit_paragraph(body)
            if chunk:
                out.append(chunk)
            body = []

        for idx, raw in enumerate(raw_lines):
            plain = _plain(raw)
            if not plain:
                flush()
                continue
            nxt = _plain(raw_lines[idx + 1]) if idx + 1 < len(raw_lines) else ""
            if allow_parish and packed:
                hit = _looks_like_parish_name(plain, packed, nxt)
                if hit:
                    flush()
                    add_masthead(hit[1], hit[0])
                    continue
            if allow_parish and _is_url_only_line(plain) and seen_parish:
                # Stitcher banner URL already shown as the parish header / grid.
                continue
            head, rest = split_heading_prefix(plain)
            if head and not rest:
                flush()
                out.append(_heading_html(head))
                continue
            if head and rest:
                flush()
                out.append(_heading_html(head))
                body.append(html.escape(rest))
                continue
            body.append(raw.strip() if "<" in raw else html.escape(plain))
        flush()

    pos = 0
    for match in _TOKEN_RE.finditer(source):
        if match.start() > pos:
            gap = source[pos : match.start()].strip()
            if gap:
                out.append(gap)
        token = match.group(0)
        if match.group(1):
            out.append(token)
            name = _plain(re.sub(r"<[^>]+>", " ", token))
            if name:
                seen_parish.add(name.split("\n")[0].lower())
        elif match.group(2):
            # Legacy accordion — flatten to masthead + body.
            name_m = re.search(r'class="parish-name"[^>]*>(.*?)</span>', token, re.I | re.S)
            body_m = re.search(r'class="parish-body"[^>]*>(.*?)</div>', token, re.I | re.S)
            if name_m:
                add_masthead(_plain(name_m.group(1)))
            if body_m:
                process_plain_lines(_BR_SPLIT_RE.split(body_m.group(1)), allow_parish=False)
            else:
                out.append(token)
        elif match.group(3):
            hm = _HEADING_TAG_RE.match(token)
            if hm:
                inner = _plain(hm.group(3))
                parish_hit = _looks_like_parish_name(inner, packed, "") if packed else None
                if parish_hit:
                    add_masthead(parish_hit[1], parish_hit[0])
                elif classify_heading_line(inner) or "b-head" in (hm.group(2) or "") or "b-title" in (hm.group(2) or "") or "ocr-parish-name" in (hm.group(2) or ""):
                    out.append(token)
                elif classify_heading_line(inner) is None and packed and parish_hit is None:
                    out.append(token)
                else:
                    out.append(token)
            else:
                out.append(token)
        elif match.group(4):
            inner = re.sub(r"^<p\b[^>]*>|</p>$", "", token, flags=re.I).strip()
            parts = [p for p in re.split(r"(?:<br\s*/?>|\n)", inner) if p.strip() or p == ""]
            # Keep blank-line splits but drop totally empty leading/trailing.
            process_plain_lines([p.strip() for p in parts if p.strip()], allow_parish=True)
        else:
            out.append(token)
        pos = match.end()
    if pos < len(source):
        gap = source[pos:].strip()
        if gap:
            out.append(gap)
    return "\n".join(part for part in _drop_empty_directory_mastheads(out) if part)


def _drop_empty_directory_mastheads(parts: list[str]) -> list[str]:
    """Drop name+URL-only blocks (mega-PDF missing-parish index), keep real bulletins."""
    kept: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if "ocr-parish-masthead" not in part:
            kept.append(part)
            i += 1
            continue
        j = i + 1
        filler = True
        while j < len(parts) and "ocr-parish-masthead" not in parts[j]:
            plain = _plain(parts[j])
            if plain and not _is_url_only_line(plain) and "ocr-failed-banner" not in parts[j]:
                filler = False
                break
            j += 1
        if filler:
            i = j
            continue
        kept.append(part)
        i += 1
    return kept


def ocr_masthead_css(selector: str) -> str:
    """Newspaper-section masthead + heading rhythm for the OCR pane."""
    return f"""
    {selector} .ocr-parish-masthead {{
      margin: 2.1em 0 1.15em;
      padding: 0.85em 0 0.7em;
      border-top: 3px solid #14524f;
      border-bottom: 1px solid #c5d0c9;
    }}
    {selector} .ocr-parish-masthead:first-child {{
      margin-top: 0;
    }}
    {selector} h2.ocr-parish-name,
    {selector} .ocr-parish-name {{
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, "Times New Roman", Times, serif;
      font-size: 1.45em;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: #14524f;
      margin: 0 0 0.2em;
      line-height: 1.25;
      border: 0;
      padding: 0;
      text-transform: none;
    }}
    {selector} .ocr-parish-date {{
      margin: 0;
      font-size: 0.88rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      color: #5a6a68;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    {selector} .ocr-parish-link {{
      margin: 0.25em 0 0;
      font-size: 0.88rem;
    }}
    {selector} h3.b-head {{
      margin-top: 1.45em;
      margin-bottom: 0.5em;
      padding-bottom: 0.12em;
      border-bottom: 1px solid #d4ddd9;
    }}
"""
