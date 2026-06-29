from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from string import Template

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "diocese_page.html"
CURRENT_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "diocese_page_current.html"
RAPHOE_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "diocese_page_raphoe.html"
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


def _build_ocr_block(ocr_text: str, *, ocr_is_html: bool = False) -> str:
    normalized = (ocr_text or "").strip() or EMPTY_OCR_TEXT
    if ocr_is_html:
        return f'<div class="ocr-body" id="ocr-text">{normalized}</div>'
    return f'<pre class="ocr-pre" id="ocr-text">{html.escape(normalized)}</pre>'


def render_diocese_raphoe_page(
    parish_links: list[dict],
    out_path: Path,
    *,
    mega_pdf_url: str,
    ocr_text: str = "",
    ocr_is_html: bool = False,
    week_label: str = "",
) -> None:
    template = Template(RAPHOE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    week_suffix = f" — {week_label}" if week_label else ""
    payload = {
        "page_title": html.escape(f"Raphoe Diocese Big Bulletin{week_suffix}"),
        "headline": "RAPHOE DIOCESE BIG BULLETIN",
        "mega_pdf_url": html.escape(mega_pdf_url, quote=True),
        "ocr_block_html": _build_ocr_block(ocr_text, ocr_is_html=ocr_is_html),
        "parish_heading": "RAPHOE PARISHES WITH WORKING BULLETIN LINKS",
        "parish_dropdown_html": _render_parish_dropdown(parish_links),
        "year": str(datetime.now(UTC).year),
        "issues_url": html.escape(ISSUES_URL, quote=True),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.safe_substitute(payload), encoding="utf-8")


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


def render_diocese_page(
    diocese_key: str,
    diocese_display_name: str,
    mega_pdf_url: str,
    ocr_text: str,
    parish_links: list[dict],
    out_path: Path,
    archive_viewer_url: str = "../../bulletins/index.html",
    ocr_standalone_url: str = "../../bulletins/index.html",
) -> None:
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    display = str(diocese_display_name or diocese_key).strip() or diocese_key
    normalized_ocr = (ocr_text or "").strip() or EMPTY_OCR_TEXT

    payload = {
        "page_title": html.escape(f"{display} Diocese Big Bulletin"),
        "diocese_display_name": html.escape(display),
        "headline": html.escape(f"{display.upper()} DIOCESE BIG BULLETIN"),
        "mega_pdf_url": html.escape(mega_pdf_url, quote=True),
        "archive_viewer_url": html.escape(archive_viewer_url, quote=True),
        "ocr_standalone_url": html.escape(ocr_standalone_url, quote=True),
        "ocr_text": html.escape(normalized_ocr),
        "parish_heading": html.escape(f"{display.upper()} PARISHES WITH WORKING BULLETIN LINKS"),
        "parish_links_html": _render_parish_links(parish_links),
        "year": str(datetime.now(UTC).year),
        "issues_url": html.escape(ISSUES_URL, quote=True),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.safe_substitute(payload), encoding="utf-8")
