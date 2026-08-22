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

from ocr.parish_splitter import (
    split_ocr_by_parish,
    split_ocr_html_by_page_ranges,
    split_ocr_html_by_parish,
)

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
    "clogher": "Clogher Diocese",
}

# Leave Holy Cross / Dunfanaghy failing — July fake dates (do not slice
# a stale bulletin onto a "this week" parish page).
SKIP_OK_PARISH_KEYS = frozenset({"holy-cross-church"})


def load_mega_page_index(pdf_path: Path | None) -> dict[str, tuple[int, int]]:
    """Read stitcher ``*.pages.json`` next to a mega PDF, if present."""
    if not pdf_path:
        return {}
    index_path = Path(pdf_path).with_name(Path(pdf_path).stem + ".pages.json")
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    parishes = data.get("parishes")
    if not isinstance(parishes, dict):
        return {}
    out: dict[str, tuple[int, int]] = {}
    for key, row in parishes.items():
        if not isinstance(row, dict):
            continue
        start, end = row.get("start_page"), row.get("end_page")
        try:
            start_i, end_i = int(start), int(end)
        except (TypeError, ValueError):
            continue
        if start_i >= 1 and end_i >= start_i:
            out[str(key)] = (start_i, end_i)
    return out


def write_missing_slice_pdf(parish_name: str, reason: str) -> bytes:
    """A real one-page PDF explaining why this parish could not be sliced."""
    buf = io.BytesIO()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except ImportError:
        # Minimal valid PDF so the viewer never 404s.
        return (
            b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 770 Td (Parish PDF unavailable) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        )
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 780, f"{parish_name} — PDF slice unavailable")
    c.setFont("Helvetica", 11)
    y = 740
    for line in (reason or "No page range could be determined.").splitlines() or [reason]:
        c.drawString(50, y, line[:110])
        y -= 16
        if y < 80:
            break
    c.setFont("Helvetica", 10)
    c.drawString(50, y - 12, "This is not the diocese collated bulletin. The parish pages could not be extracted.")
    c.save()
    return buf.getvalue()


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
        if str(key) in SKIP_OK_PARISH_KEYS:
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
    preserve_existing_pdfs: bool = False,
) -> list[str]:
    """Generate one bulletin page per currently-"ok" parish in *diocese_key*.

    *pdf_path* is the diocese's local mega PDF and *raw_ocr_fragment* is its
    OCR HTML **before** ``tighten_ocr_paragraphs`` regroups paragraphs (see
    :func:`ocr.generate_bulletin_pages.write_viewer_page`, which has both on
    hand already) — both come from the single existing harvest+OCR run, no
    re-fetch or re-OCR happens here.

    Page ranges come first from the stitcher's ``*.pages.json`` (authoritative),
    then from name-marker matching in the mega OCR HTML. If a parish is ``ok``
    but cannot be sliced, the page says so with a real reason and a local
    one-page explanation PDF — it does **not** pretend the diocese mega is
    this parish's bulletin, and it does not link to a missing 404 file.

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
    page_index = load_mega_page_index(pdf_path)
    if page_index:
        html_chunks = split_ocr_html_by_page_ranges(raw_ocr_fragment, page_index)
        for key, (start, end) in page_index.items():
            chunk = html_chunks.get(key)
            if chunk is None:
                continue
            if chunk.start_page is None:
                html_chunks[key] = chunk._replace(start_page=start, end_page=end)
    else:
        html_chunks = split_ocr_html_by_parish(raw_ocr_fragment, entries)
    plain_text = _fragment_to_plain_text(tighten_ocr_paragraphs(raw_ocr_fragment or ""))
    text_chunks = split_ocr_by_parish(plain_text, entries)

    mega_exists = bool(pdf_path and Path(pdf_path).exists())
    try:
        total_pages = count_pdf_pages(pdf_path) if mega_exists else 0
    except Exception:
        total_pages = 0
        mega_exists = False

    out_root = out_dir or (PARISHES_OUT_DIR / diocese_key)
    out_root.mkdir(parents=True, exist_ok=True)

    diocese_label = config.display_name.replace(" Diocese", "").upper()
    uk_date = format_uk_date(bulletin_date)
    written: list[str] = []

    for parish in parishes:
        chunk = html_chunks.get(parish.key)
        indexed = page_index.get(parish.key)
        start_page = (indexed[0] if indexed else None) or (chunk.start_page if chunk else None)
        end_page = (indexed[1] if indexed else None) or (chunk.end_page if chunk else None)
        has_range = bool(start_page and end_page)
        pdf_bytes = (
            slice_pdf_pages(pdf_path, start_page, end_page)
            if (has_range and mega_exists and total_pages)
            else None
        )
        if pdf_bytes is not None and len(pdf_bytes) < 32:
            pdf_bytes = None

        base_meta = (
            f"This week's bulletin for {parish.display_name} — {uk_date}. "
            f"Part of the {config.display_name} collated bulletin."
        )
        if pdf_bytes:
            pdf_out = out_root / f"{parish.key}.pdf"
            existing_ok = (
                preserve_existing_pdfs
                and pdf_out.exists()
                and pdf_out.stat().st_size > 2048
            )
            if not existing_ok:
                pdf_out.write_bytes(pdf_bytes)
            pdf_href = f"{parish.key}.pdf"
            meta_line = base_meta
            fail_reason = ""
        else:
            if not mega_exists:
                fail_reason = (
                    "The diocese mega PDF is missing from the repository, so this parish's "
                    "pages could not be sliced."
                )
            elif not has_range:
                fail_reason = (
                    "This parish is marked OK, but its page range could not be found in this "
                    "week's mega OCR (no stitcher page index and no name-banner match)."
                )
            else:
                fail_reason = (
                    "This parish is marked OK and a page range was found, but slicing those "
                    "pages from the mega PDF failed."
                )
            (out_root / f"{parish.key}.pdf").write_bytes(
                write_missing_slice_pdf(parish.display_name, fail_reason)
            )
            pdf_href = f"{parish.key}.pdf"
            meta_line = f"{base_meta} {fail_reason}"

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
                why = fail_reason or (
                    "No searchable text was found for this parish in this week's mega OCR."
                )
                ocr_fragment = (
                    '<div class="ocr-failed-banner" role="status">'
                    f"⚠️ {html.escape(why)}</div>"
                )

        from ocr.bulletin_layout import structure_ocr_html

        ocr_fragment = structure_ocr_html(
            tighten_ocr_paragraphs(ocr_fragment),
            bulletin_date=bulletin_date,
            single_parish_name=parish.display_name,
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
