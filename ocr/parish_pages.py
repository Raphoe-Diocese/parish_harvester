from __future__ import annotations

"""Per-parish bulletin pages — one page per currently-working ("ok") parish.

Scoped-down siblings of the diocese "big bulletin" viewer page
(:func:`ocr.generate_bulletin_pages.render_bulletin_viewer_shell`), showing
just *that* parish's own PDF pages and OCR text instead of the whole
diocese's collated mega bulletin.

Reuses the "OCR once, reuse everywhere" pipeline end to end — no re-OCR, no
re-fetch. The diocese's mega PDF and its single OCR pass are sliced per
parish using :func:`ocr.parish_splitter.split_ocr_html_by_parish`, which
locates each parish's own name-marker line in the already-generated OCR HTML
and reports the mega-PDF page range it spans (every mega-PDF page is added
whole to exactly one parish's block by
:func:`harvester.stitcher.stitch_mega_pdf`, so page-label boundaries are
exact once the name marker is found).

Parishes are sourced from ``parishes/parish_status.json`` — the single
source of truth for "is this parish currently working?" — filtered to
``outcome == "ok"``. This list is expected to drift week to week, so nothing
here is hardcoded to a fixed parish roster.
"""

import html
import io
import json
from dataclasses import dataclass
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from ocr.parish_splitter import split_ocr_by_parish, split_ocr_html_by_parish

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
PARISHES_OUT_DIR = DOCS_DIR / "parishes"
PARISH_STATUS_PATH = REPO_ROOT / "parishes" / "parish_status.json"

# parish_status.json's `diocese` field uses the full display name; map the
# short config keys used everywhere else in ocr/generate_bulletin_pages.py.
DIOCESE_STATUS_NAMES = {
    "raphoe": "Raphoe Diocese",
    "derry": "Derry Diocese",
    "down_and_connor": "Down & Connor Diocese",
}


@dataclass(frozen=True)
class OkParish:
    key: str
    display_name: str
    url: str


def load_ok_parishes(diocese_key: str, parish_status_path: Path | None = None) -> list[OkParish]:
    """Every parish in *diocese_key* with ``outcome == "ok"`` this week, A-Z."""
    path = parish_status_path or PARISH_STATUS_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    parishes = data.get("parishes")
    if not isinstance(parishes, dict):
        return []
    target_diocese = DIOCESE_STATUS_NAMES.get(diocese_key, diocese_key)
    out: list[OkParish] = []
    for key, row in parishes.items():
        if not isinstance(row, dict):
            continue
        if row.get("outcome") != "ok":
            continue
        if row.get("diocese") != target_diocese:
            continue
        display_name = str(row.get("display_name") or key).strip() or str(key)
        url = str(row.get("url") or "").strip()
        out.append(OkParish(key=str(key), display_name=display_name, url=url))
    out.sort(key=lambda p: p.display_name.lower())
    return out


def slice_pdf_pages(pdf_path: Path, start_page: int, end_page: int) -> bytes | None:
    """Extract 1-indexed inclusive pages ``[start_page, end_page]`` from
    *pdf_path* into a small standalone PDF. Returns ``None`` on any error
    (missing/corrupt PDF) so callers can fall back gracefully."""
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return None
    total = len(reader.pages)
    if total == 0:
        return None
    start = max(1, min(int(start_page), total))
    end = max(start, min(int(end_page), total))
    writer = PdfWriter()
    for idx in range(start - 1, end):
        writer.add_page(reader.pages[idx])
    buf = io.BytesIO()
    try:
        writer.write(buf)
    except Exception:
        return None
    return buf.getvalue()


def _render_other_parishes_grid(parishes: list[OkParish], current_key: str) -> str:
    """Internal A-Z link grid to this diocese's other parish pages (same
    directory, relative hrefs) — the per-parish sibling of
    :func:`ocr.generate_bulletin_pages.render_parish_link_grid`."""
    others = [p for p in parishes if p.key != current_key]
    if not others:
        return '<p class="empty-state">No other parish bulletin pages are available yet for this diocese.</p>'
    items = []
    blank = 'target="_blank" rel="noopener noreferrer"'
    for parish in others:
        href = f"{parish.key}.html"
        items.append(
            (
                '<li class="parish-item" data-name="{name_key}">'
                '<a class="parish-link" href="{href}" {blank}>{name}</a></li>'
            ).format(
                name_key=html.escape(parish.display_name.lower(), quote=True),
                href=html.escape(href, quote=True),
                name=html.escape(parish.display_name),
                blank=blank,
            )
        )
    return (
        '<div id="parish-empty" class="empty-state" hidden>No matching parishes found.</div>'
        f'<ul id="parish-grid" class="parish-grid">{"".join(items)}</ul>'
    )


def write_parish_pages_for_diocese(
    diocese_key: str,
    bulletin_date: str,
    pdf_path: Path,
    raw_ocr_fragment: str,
    diocese_pdf_href: str,
    out_dir: Path | None = None,
    parish_status_path: Path | None = None,
) -> list[str]:
    """Generate one bulletin page per currently-"ok" parish in *diocese_key*.

    *pdf_path* is the diocese's local mega PDF and *raw_ocr_fragment* is its
    OCR HTML **before** ``tighten_ocr_paragraphs`` regroups paragraphs (see
    :func:`ocr.generate_bulletin_pages.write_viewer_page`, which has both on
    hand already) — both come from the single existing harvest+OCR run, no
    re-fetch or re-OCR happens here. *diocese_pdf_href* is used as a graceful
    fallback ``pdf_href`` for any parish whose page range could not be
    determined this week (rare — OCR must have read that parish's stitched
    banner line — but always visible/honest when it happens, never silently
    wrong).

    Returns the list of parish keys a page was written for.
    """
    from ocr.generate_bulletin_pages import (
        DIOCESES,
        DioceseConfig,
        _fragment_to_plain_text,
        count_pdf_pages,
        format_uk_date,
        render_bulletin_viewer_shell,
        render_ocr_standalone_page,
        render_pdf_standalone_page,
        tighten_ocr_paragraphs,
    )

    config = DIOCESES[diocese_key]
    parishes = load_ok_parishes(diocese_key, parish_status_path)
    if not parishes:
        return []

    entries = [(p.key, p.display_name) for p in parishes]
    html_chunks = split_ocr_html_by_parish(raw_ocr_fragment, entries)
    plain_text = _fragment_to_plain_text(tighten_ocr_paragraphs(raw_ocr_fragment or ""))
    text_chunks = split_ocr_by_parish(plain_text, entries)

    try:
        total_pages = count_pdf_pages(pdf_path) if pdf_path and Path(pdf_path).exists() else 0
    except Exception:
        total_pages = 0

    out_root = out_dir or (PARISHES_OUT_DIR / diocese_key)
    out_root.mkdir(parents=True, exist_ok=True)

    diocese_label = config.display_name.replace(" Diocese", "").upper()
    uk_date = format_uk_date(bulletin_date)
    written: list[str] = []

    for parish in parishes:
        chunk = html_chunks.get(parish.key)
        has_range = bool(chunk and chunk.start_page and chunk.end_page)
        pdf_bytes = slice_pdf_pages(pdf_path, chunk.start_page, chunk.end_page) if (has_range and total_pages) else None

        base_meta = (
            f"This week's bulletin for {parish.display_name} — {uk_date}. "
            f"Part of the {config.display_name} collated bulletin."
        )
        if pdf_bytes:
            (out_root / f"{parish.key}.pdf").write_bytes(pdf_bytes)
            pdf_href = f"{parish.key}.pdf"
            meta_line = base_meta
        else:
            pdf_href = diocese_pdf_href
            meta_line = (
                f"{base_meta} (Exact PDF pages for this parish could not be auto-detected this "
                "week, so this links to the full diocese bulletin instead.)"
            )

        if chunk and chunk.html.strip():
            ocr_fragment = chunk.html
        else:
            fallback_text = (text_chunks.get(parish.key) or "").strip()
            if fallback_text:
                lines = [html.escape(ln) for ln in fallback_text.splitlines() if ln.strip()]
                ocr_fragment = (
                    '<div class="ocr-failed-banner" role="status">'
                    "ℹ️ Matched by parish name only (not exact PDF pages) this week — check the "
                    "PDF above for the definitive version.</div>\n"
                    "<p>" + "<br>\n".join(lines) + "</p>"
                )
            else:
                ocr_fragment = (
                    '<div class="ocr-failed-banner" role="status">'
                    "⚠️ No searchable text was found for this parish this week. Please use the "
                    "PDF above.</div>"
                )

        parish_config = DioceseConfig(
            key=parish.key,
            display_name=parish.display_name,
            headline=f"{parish.display_name} Parish Bulletin",
            evidence_path=config.evidence_path,
            pdf_filename=f"{parish.key}.pdf",
        )
        pdf_standalone_href = f"{parish.key}-pdf.html"
        ocr_standalone_href = f"{parish.key}-ocr.html"
        viewer_filename = f"{parish.key}.html"

        page_html = render_bulletin_viewer_shell(
            page_title=f"{parish.display_name} Bulletin — {uk_date}",
            diocese_label=diocese_label,
            display_name=parish.display_name,
            headline=f"{parish.display_name} Parish Bulletin",
            meta_line=meta_line,
            back_href=f"../../dioceses/{diocese_key}/index.html",
            back_label=f"← Back to {config.display_name} bulletin",
            pdf_href=pdf_href,
            pdf_download_href=pdf_href,
            pdf_standalone_href=pdf_standalone_href,
            ocr_standalone_href=ocr_standalone_href,
            ocr_fragment=ocr_fragment,
            parish_section_heading=f"Other {diocese_label} Parishes",
            parish_links_html=_render_other_parishes_grid(parishes, parish.key),
        )
        (out_root / viewer_filename).write_text(page_html, encoding="utf-8")
        (out_root / f"{parish.key}-pdf.html").write_text(
            render_pdf_standalone_page(parish_config, bulletin_date, pdf_href=pdf_href, viewer_href=viewer_filename),
            encoding="utf-8",
        )
        (out_root / f"{parish.key}-ocr.html").write_text(
            render_ocr_standalone_page(parish_config, bulletin_date, ocr_fragment, viewer_href=viewer_filename),
            encoding="utf-8",
        )
        written.append(parish.key)

    return written
