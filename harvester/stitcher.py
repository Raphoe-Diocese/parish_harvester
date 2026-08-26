"""
stitcher.py — Mega PDF stitcher for the Parish Bulletin Harvester.

Merges all downloaded PDFs (A-Z) into one mega PDF.
The “Missing & Online-Only” list lives on the diocese page intro,
not as a last page of this PDF (Frank, 23/08/2026).
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import FetchResult


# Characters that are considered "filler" and should not count as real content
# when deciding whether a PDF page is blank/near-blank.
# Covers whitespace, ALL ASCII control chars (incl. form feed \x0c),
# invisible Unicode (NBSP, soft-hyphen, zero-width chars, BOM),
# bullets, dashes, smart-quotes, ellipsis, and standalone punctuation.
_FILLER_PATTERN = re.compile(
    r'[\s\x00-\x1f\x7f\xa0\xad'
    r'\u200b\u200c\u200d\ufeff'
    r'\u2022\u00b7\u2019\u2018\u2026\u2013\u2014'
    r'.,:;!?\-_|]+')
# Minimum number of meaningful characters for a page to be kept.
# Real bulletin pages always contain hundreds of characters; this threshold
# catches truly blank pages (0 chars), dot/dash separator pages,
# near-blank pages with only a page number, and control-character-only pages.
_MIN_MEANINGFUL_CHARS = 30
# Website error/security/captcha pages saved as a "PDF" (e.g. via print-to-PDF
# on a blocked page) always carry one of these exact phrases and are always
# short. Real bulletin pages never match this combination, so this only
# rejects genuine junk — it never touches real (incl. Irish/bilingual) content.
_ERROR_PAGE_PATTERN = re.compile(
    r"(?i)(?:security\s*check|403\s*-?\s*forbidden|access denied|"
    r"page not found|404\s*(?:error|not found)|verify you are human|"
    r"i['\u2019]?m not a robot|unusual traffic|checking your browser|captcha)"
)
_ERROR_PAGE_MAX_CHARS = 1500
# Parish bulletins are never longer than 4 pages by default.  Any PDF with more
# pages is almost certainly a full document (parish magazine, booklet, etc.)
# that was accidentally downloaded instead of the weekly bulletin. Individual
# recipes may raise this via ``max_bulletin_pages`` (e.g. Ardmore's normal
# 9-page weekly PDF).
_MAX_BULLETIN_PAGES = 4


def _max_bulletin_pages_for_parish(parish_key: str) -> int:
    """Load recipe ``max_bulletin_pages`` for *parish_key*, else the global 4."""
    try:
        from .config import MAX_BULLETIN_PAGES, PARISHES_DIR
        from .fetcher import recipe_max_bulletin_pages
        from .replay import recipe_path_for
    except Exception:
        return _MAX_BULLETIN_PAGES
    try:
        path = recipe_path_for(parish_key, PARISHES_DIR)
        if not path.exists():
            return MAX_BULLETIN_PAGES
        data = json.loads(path.read_text(encoding="utf-8"))
        return recipe_max_bulletin_pages(data if isinstance(data, dict) else None)
    except Exception:
        return _MAX_BULLETIN_PAGES


_HEADER_BANNER_HEIGHT = 18
_HEADER_TOP_MARGIN = 8
_HEADER_SIDE_MARGIN = 20
_HEADER_RULE_SIDE_PADDING = 16
_HEADER_BACKGROUND_ALPHA = 0.75
_HEADER_BACKGROUND_OFFSET = 4


def format_uk_date(iso_date: str) -> str:
    raw = str(iso_date or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if not match:
        return raw
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"


def _xml_escape(text: str) -> str:
    """Escape XML/HTML special characters for use in ReportLab markup."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _absolute_http_url(url: str | None) -> str | None:
    """Parish header links must be clickable http(s) URLs, not bare hostnames."""
    raw = (url or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    if raw.startswith("//"):
        return "https:" + raw
    if " " in raw:
        return None
    if raw.startswith("www.") or "." in raw:
        return "https://" + raw.lstrip("/")
    return None


def _build_parish_header_pdf(
    display_name: str,
    website: str | None,
    pagesize: tuple[float, float],
    colors_module,
    canvas_module,
) -> io.BytesIO:
    """Create a transparent top-banner overlay with parish name + website link."""
    buf = io.BytesIO()
    width, height = pagesize
    c = canvas_module.Canvas(buf, pagesize=pagesize)

    banner_h = _HEADER_BANNER_HEIGHT
    top = height - _HEADER_TOP_MARGIN
    c.setFillColor(colors_module.Color(1, 1, 1, alpha=_HEADER_BACKGROUND_ALPHA))
    c.rect(0, height - banner_h - _HEADER_BACKGROUND_OFFSET, width, banner_h + _HEADER_BACKGROUND_OFFSET, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors_module.black)
    c.drawString(_HEADER_SIDE_MARGIN, top - 8, display_name)

    link_href = _absolute_http_url(website)
    if link_href:
        label = website if website.startswith(("http://", "https://", "www.")) else link_href
        c.setFont("Helvetica", 8)
        c.setFillColor(colors_module.blue)
        c.drawRightString(width - _HEADER_SIDE_MARGIN, top - 8, label)
        text_w = c.stringWidth(label, "Helvetica", 8)
        c.linkURL(
            link_href,
            (
                width - _HEADER_SIDE_MARGIN - text_w,
                top - 16,
                width - _HEADER_SIDE_MARGIN,
                top + 3,
            ),
            relative=0,
            thickness=0,
            color=colors_module.blue,
            newWindow=True,
        )

    c.setStrokeColor(colors_module.Color(0.85, 0.85, 0.85))
    c.line(_HEADER_RULE_SIDE_PADDING, height - banner_h - _HEADER_BACKGROUND_OFFSET, width - _HEADER_RULE_SIDE_PADDING, height - banner_h - _HEADER_BACKGROUND_OFFSET)
    c.save()
    buf.seek(0)
    return buf


def stitch_mega_pdf(
    results: list["FetchResult"],
    current_dir: Path,
    bulletins_dir: Path,
    target: date,
    contacts_path: Path | None = None,
    mega_excludes_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """
    Merge all downloaded PDFs (A-Z by display name) into one mega PDF.
    Alias recipes (Ballintra → Drumholm, Kilmacrenan → Gartan/Termon) are
    skipped so the same parish is not listed twice. HTML-only / unavailable
    parishes are *not* appended as a last page — that list is on the
    diocese page intro.

    *mega_excludes_path* points to an optional JSON array of parish keys to
    skip in the mega PDF (e.g. when a parish posted a stale bulletin).  The
    file is typically ``parishes/mega_excludes.json`` and can be edited from
    the browser extension without rerunning the recipe.

    *output_path* overrides the default ``bulletins_dir/all_bulletins_{target}.pdf``
    output location (used for per-diocese mega PDFs).
    """
    try:
        import PyPDF2
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        print(f"  ⚠️  Skipping mega PDF — missing library: {exc}")
        return

    # Load parish contacts for display names / website links
    contacts: dict = {}
    if contacts_path and contacts_path.exists():
        try:
            contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ⚠️  Could not load contacts file: {exc}")

    # Load mega-PDF exclude list (parish keys to skip for this run)
    mega_excludes: set[str] = set()
    if mega_excludes_path and mega_excludes_path.exists():
        try:
            raw_excludes = json.loads(mega_excludes_path.read_text(encoding="utf-8"))
            if isinstance(raw_excludes, list):
                mega_excludes = {str(k).strip() for k in raw_excludes if k}
                if mega_excludes:
                    print(f"  ℹ️  Mega-PDF excludes ({len(mega_excludes)}): {', '.join(sorted(mega_excludes))}")
        except Exception as exc:
            print(f"  ⚠️  Could not load mega_excludes.json: {exc}")

    from harvester.parish_aliases import combined_display_name, is_alias_key

    # Build map: key -> (pdf_path | None, url, display_name)
    parish_map: dict[str, tuple[Path | None, str, str]] = {}
    for r in results:
        key = r.key
        if is_alias_key(key):
            continue
        # Keep stale historical fallback results out of the mega PDF.
        if r.is_fallback:
            continue
        # Reject bulletins flagged stale by freshness safety net.
        if r.is_stale:
            print(f"    ⏭️  Skipping {key} (stale bulletin — excluded from mega PDF)")
            continue
        # Skip parishes explicitly excluded by the operator
        elif key in mega_excludes:
            print(f"    ⏭️  Skipping {key} (in mega-PDF exclude list)")
            continue
        if r.status == "ok" and r.file_path:
            pdf_path: Path | None = current_dir / r.file_path.name
            if not (pdf_path and pdf_path.exists()):
                pdf_path = None
            parish_map[key] = (pdf_path, r.url, r.display_name)
        elif r.status == "html_link":
            parish_map[key] = (None, r.url, r.display_name)
        else:
            parish_map.setdefault(key, (None, r.url, r.display_name))

    # Sort A-Z by human display name (not domain key)
    sorted_entries = sorted(
        parish_map.items(),
        key=lambda item: item[1][2].lower() if item[1][2] else item[0].lower()
    )

    output_path = output_path or (bulletins_dir / f"all_bulletins_{target}.pdf")
    merger = PyPDF2.PdfWriter()
    real_count = 0
    page_ranges: dict[str, dict[str, str | int]] = {}

    # Collect parishes without a PDF (logged only — listed on the diocese page)
    missing_entries: list[tuple[str, str, str | None]] = []

    for parish_key, (pdf_path, parish_url, display_name) in sorted_entries:
        info = contacts.get(parish_key, {})
        if not display_name:
            display_name = info.get("display_name") or parish_key.replace("_", " ").title()
        display_name = combined_display_name(parish_key) or display_name
        website: str | None = info.get("website")

        if pdf_path and pdf_path.exists():
            try:
                link_url = _absolute_http_url(website) or _absolute_http_url(parish_url)
                reader = PyPDF2.PdfReader(str(pdf_path))
                page_count = len(reader.pages)
                page_limit = _max_bulletin_pages_for_parish(parish_key)
                if page_count > page_limit:
                    print(
                        f"    ⚠️  Skipping {parish_key}: {page_count} pages exceeds "
                        f"the {page_limit}-page bulletin limit (likely a full document)"
                    )
                    missing_entries.append((display_name, parish_url, website))
                    continue
                start_page = len(merger.pages) + 1
                for idx, page in enumerate(reader.pages):
                    if idx == 0:
                        page_w = float(page.mediabox.width)
                        page_h = float(page.mediabox.height)
                        header_pdf = _build_parish_header_pdf(
                            display_name,
                            link_url,
                            (page_w, page_h),
                            colors,
                            canvas,
                        )
                        header_reader = PyPDF2.PdfReader(header_pdf)
                        if header_reader.pages:
                            page.merge_page(header_reader.pages[0])
                    # Skip blank or near-blank pages (no real text content).
                    # Strips all invisible/filler characters before counting —
                    # catches form-feed-only pages, dot-separator pages, etc.
                    try:
                        text = page.extract_text() or ""
                        meaningful = _FILLER_PATTERN.sub('', text)
                        if len(meaningful) < _MIN_MEANINGFUL_CHARS:
                            continue
                        if (
                            len(meaningful) < _ERROR_PAGE_MAX_CHARS
                            and _ERROR_PAGE_PATTERN.search(text)
                        ):
                            print(
                                f"    ⚠️  Skipping a page for {parish_key}: looks like a "
                                "website error/security page, not a bulletin"
                            )
                            continue
                    except Exception:
                        pass  # If we can't extract text, include the page to be safe
                    merger.add_page(page)
                end_page = len(merger.pages)
                if end_page >= start_page:
                    page_ranges[parish_key] = {
                        "display_name": display_name,
                        "start_page": start_page,
                        "end_page": end_page,
                    }
                real_count += 1
            except Exception as exc:
                print(f"    ⚠️  Could not merge {parish_key}: {exc}")
                missing_entries.append((display_name, parish_url, website))
        else:
            missing_entries.append((display_name, parish_url, website))

    # Missing / online-only parishes are listed on the diocese page intro,
    # not as a last sheet of this mega PDF.
    if missing_entries:
        print(
            f"     Online-only    : {len(missing_entries)} "
            "(shown on the diocese page, not in this PDF)"
        )

    if real_count > 0:
        bulletins_dir.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            merger.write(fh)
        try:
            from harvester.pdf_compress import compress_pdf_inplace

            compress_pdf_inplace(output_path)
        except Exception as exc:
            print(f"     ⚠️  Mega PDF compress skipped: {exc}")
        index_payload = {
            "date": target.isoformat(),
            "pdf": output_path.name,
            "parishes": page_ranges,
        }
        index_path = output_path.with_name(output_path.stem + ".pages.json")
        index_path.write_text(json.dumps(index_payload, indent=2) + "\n", encoding="utf-8")
        print(f"  📖 Mega PDF      : {output_path}")
        print(f"     Page index     : {index_path} ({len(page_ranges)} parish range(s))")
        print(f"     Real PDFs      : {real_count}")
        publish_mega_to_docs(output_path)
    else:
        print("  ⚠️  No pages to include in mega PDF — skipping.")


def publish_mega_to_docs(pdf_path: Path, docs_mega_dir: Path | None = None) -> Path | None:
    """Copy a diocese mega PDF + page index into ``docs/mega_pdf`` for Pages.

    Only publishes files named ``*_mega_bulletin.pdf`` so test stitcher
    outputs (``all_bulletins_*.pdf``) stay out of the public docs tree.
    """
    import shutil

    pdf_path = Path(pdf_path)
    if not pdf_path.exists() or not pdf_path.name.endswith("_mega_bulletin.pdf"):
        return None
    dest_dir = docs_mega_dir or (Path(__file__).resolve().parent.parent / "docs" / "mega_pdf")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / pdf_path.name
    shutil.copy2(pdf_path, dest)
    index_src = pdf_path.with_name(pdf_path.stem + ".pages.json")
    if index_src.exists():
        shutil.copy2(index_src, dest_dir / index_src.name)
    print(f"     Published     : {dest}")
    return dest
