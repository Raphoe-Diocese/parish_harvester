from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from string import Template

CURRENT_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "diocese_page_current.html"
ISSUES_URL = "https://github.com/Raphoe-Diocese/parish_harvester/issues/new"
EMPTY_OCR_TEXT = "We're still collecting OCR text for this diocese. Check back next Sunday."
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Raphoe-Diocese/parish_harvester/main/Bulletins/current"


def _render_parish_links(
    parish_links: list[dict],
    *,
    with_status: bool = False,
    preserve_order: bool = False,
) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish links available yet.</p>'

    items: list[str] = []
    ordered = parish_links
    if not preserve_order:
        ordered = sorted(parish_links, key=lambda item: str(item.get("name") or "").lower())
    for link in ordered:
        name = html.escape(str(link.get("name") or "Unnamed Parish"))
        url = html.escape(str(link.get("url") or "#"), quote=True)
        status = str(link.get("status") or "").strip().lower()
        css = "ok" if status == "ok" else ("miss" if status else "")
        li_class = f' class="{css}"' if with_status and css else ""
        suffix = " ✓" if status == "ok" else ""
        items.append(
            f'<li{li_class}><a href="{url}" target="_blank" rel="noopener noreferrer">{name}{suffix}</a></li>'
        )
    return f'<ul class="parish-list">{"".join(items)}</ul>'


def _render_parish_dropdown(parish_links: list[dict]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish links available yet.</p>'

    options = ['<option value="">Choose a parish…</option>']
    for link in sorted(parish_links, key=lambda item: str(item.get("name") or "").lower()):
        name = html.escape(str(link.get("name") or "Unnamed Parish"))
        url = html.escape(str(link.get("url") or ""), quote=True)
        if not url:
            continue
        options.append(f'<option value="{url}">{name}</option>')

    return (
        '<div class="parish-picker">'
        f'<select id="parish-select" class="parish-dropdown" aria-label="Choose a parish bulletin">{"".join(options)}</select>'
        '<a id="parish-open" class="parish-open-btn" href="#" target="_blank" rel="noopener noreferrer" aria-disabled="true">Open parish bulletin</a>'
        "</div>"
    )


def _clean_embedded_ocr_html(fragment: str) -> str:
    """Remove OCR UI artefacts before embedding on diocese pages."""
    text = fragment or ""
    text = re.sub(r'<p\s+class="page-label"[^>]*>.*?</p>', "", text, flags=re.I | re.S)
    text = re.sub(r">Parish newsletter\s*↗?<", ">Newsletter<", text, flags=re.I)
    # Normalize / strip repeated empty-state and newsletter lines inside bodies.
    empty_msg = "No searchable text available this week."
    text = re.sub(
        r"No text this week\s*[—\-–]?\s*use the newsletter link\.?",
        empty_msg,
        text,
        flags=re.I,
    )
    text = re.sub(
        r"No searchable bulletin text for this parish this week\.[^.]*\.?",
        empty_msg,
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(?:Parish newsletter\s*↗?|Newsletter)(?:\s*<br\s*/?>\s*)+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"(?:{re.escape(empty_msg)}(?:\s*<br\s*/?>\s*)?)+",
        empty_msg,
        text,
        flags=re.I,
    )
    # If a parish body is only the empty message (possibly glued to a name), normalize.
    text = re.sub(
        rf'(<div class="parish-body">)\s*<p[^>]*>\s*(?:{re.escape(empty_msg)})+\s*[A-Za-zÀ-ÿ\'’&\- ]{{0,40}}\s*(?:{re.escape(empty_msg)})*\s*</p>\s*(</div>)',
        rf'\1<p class="parish-empty">{empty_msg}</p>\2',
        text,
        flags=re.I,
    )
    text = re.sub(
        rf'(<div class="parish-body">)\s*<p(?![^>]*parish-empty)[^>]*>\s*{re.escape(empty_msg)}\s*</p>\s*(</div>)',
        rf'\1<p class="parish-empty">{empty_msg}</p>\2',
        text,
        flags=re.I,
    )
    text = re.sub(r"<p>\s*</p>", "", text, flags=re.I)
    return text.strip()


def _build_ocr_fragment(ocr_text: str, *, ocr_is_html: bool = False) -> str:
    """Prepare OCR content for the shared ``#ocr-panel`` slot (see ocr.generate_bulletin_pages)."""
    normalized = (ocr_text or "").strip() or EMPTY_OCR_TEXT
    if ocr_is_html:
        return _clean_embedded_ocr_html(normalized)
    return f'<pre style="white-space:pre-wrap;margin:0;font-family:inherit;">{html.escape(normalized)}</pre>'


def render_diocese_raphoe_page(
    parish_links: list[dict],
    out_path: Path,
    *,
    mega_pdf_url: str,
    ocr_text: str = "",
    ocr_is_html: bool = False,
    week_label: str = "",
    diocese_display_name: str = "Raphoe Diocese",
    headline: str = "Raphoe Collated Bulletin",
    ocr_standalone_url: str = "../../bulletins/index.html",
    pdf_standalone_url: str = "",
    internal_parish_hrefs: dict[str, str] | None = None,
) -> None:
    """Render a diocese's "current" landing page.

    Uses :func:`ocr.generate_bulletin_pages.render_bulletin_viewer_shell` — the
    same canonical PDF + Text Bulletin viewer design used for the dated
    bulletin-archive pages — so Raphoe, Derry and Down & Connor always look
    and behave identically. Despite the historical function name this now
    renders every live diocese's page, not just Raphoe's.

    *internal_parish_hrefs* optionally maps a normalised parish name to this
    diocese's own generated per-parish bulletin page (see
    :mod:`ocr.parish_pages`) — see
    :func:`ocr.generate_bulletin_pages.render_parish_link_grid`.
    """
    from ocr.generate_bulletin_pages import render_bulletin_viewer_shell, render_parish_link_grid

    week_suffix = f" — {week_label}" if week_label else ""
    display = str(diocese_display_name or "Diocese").strip()
    short = display.removesuffix(" Diocese").strip() or display
    if short == "Down and Connor":
        short = "Down & Connor"
    diocese_label = short.upper()
    meta_line = f"This week's bulletin — {week_label}." if week_label else "Updated automatically every Sunday."
    pdf_url = str(mega_pdf_url or "").strip()

    tuple_links = [
        (str(link.get("name") or "Unnamed Parish"), str(link.get("url") or ""))
        for link in parish_links
    ]

    html_doc = render_bulletin_viewer_shell(
        page_title=f"{display} Collated Bulletin{week_suffix}",
        diocese_label=diocese_label,
        display_name=display,
        headline=headline,
        meta_line=meta_line,
        back_href="../../index.html",
        back_label="← Back to home",
        pdf_href=pdf_url,
        pdf_download_href=pdf_url,
        pdf_standalone_href=str(pdf_standalone_url or "").strip() or pdf_url,
        ocr_standalone_href=str(ocr_standalone_url or "").strip(),
        ocr_fragment=_build_ocr_fragment(ocr_text, ocr_is_html=ocr_is_html),
        parish_section_heading=f"{diocese_label} Parishes with Working Bulletin Links",
        parish_links_html=render_parish_link_grid(tuple_links, internal_hrefs=internal_parish_hrefs),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


def render_diocese_current_page(
    diocese_display_name: str,
    parish_links: list[dict],
    out_path: Path,
    *,
    week_label: str = "this Sunday",
    ok_count: int = 0,
    skip_count: int = 0,
    fail_count: int = 0,
    links_only: bool = False,
    preserve_order: bool = False,
) -> None:
    template = Template(CURRENT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    display = str(diocese_display_name or "").strip() or "Diocese"
    week_note = (
        "Tap a parish to open its bulletin page."
        if links_only
        else f"This week's parish bulletins — {week_label}. Tap a parish to open its bulletin PDF."
    )
    stats_html = ""
    if not links_only:
        stats_html = (
            '<div class="stats">'
            f'<span class="stat">✅ {ok_count} downloaded</span>'
            f'<span class="stat">⏭️ {skip_count} skipped</span>'
            f'<span class="stat">❌ {fail_count} need attention</span>'
            "</div>"
        )
    payload = {
        "page_title": html.escape(f"{display} — Parish Bulletins"),
        "headline": html.escape(f"{display.upper()} PARISH BULLETINS"),
        "week_note": html.escape(week_note),
        "stats_html": stats_html,
        "parish_heading": html.escape(f"{display.upper()} PARISHES"),
        "parish_links_html": _render_parish_links(
            parish_links,
            with_status=not links_only,
            preserve_order=preserve_order,
        ),
        "year": str(datetime.now(UTC).year),
        "issues_url": html.escape(ISSUES_URL, quote=True),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.safe_substitute(payload), encoding="utf-8")
