from __future__ import annotations

import argparse
import json
import html
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from PyPDF2 import PdfReader

from harvester.ai_summaries import summarise_bulletin
from harvester.events_extractor import extract_events, write_events_json
from harvester.weekly_diff import diff_bulletins
from ocr.parish_splitter import split_ocr_by_parish

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
BULLETINS_DIR = DOCS_DIR / "bulletins"
BULLETINS_DATA_DIR = REPO_ROOT / "Bulletins"
SUMMARIES_DIR = BULLETINS_DATA_DIR / "summaries"
DIFFS_DIR = BULLETINS_DATA_DIR / "diffs"
CONTACTS_PATH_BY_DIOCESE = {
    "derry": REPO_ROOT / "parishes" / "derry_diocese_contacts.json",
    "down_and_connor": REPO_ROOT / "parishes" / "down_and_connor_contacts.json",
    "raphoe": REPO_ROOT / "parishes" / "raphoe_diocese_contacts.json",
}

HEADER_PATTERN = re.compile(r"^#\s*---\s*(.*?)\s*---\s*$")
OCR_BODY_PATTERN = re.compile(r'<div class="scrollable-viewer">\s*(.*?)\s*</div>\s*</body>', re.DOTALL | re.IGNORECASE)
OCR_PAGE_HEADING_PATTERN = re.compile(r"<h2>\s*Page\s+(\d+)\s*</h2>", re.IGNORECASE)
VIEWER_FILE_PATTERN = re.compile(r"^([a-z0-9_]+)-(\d{4}-\d{2}-\d{2})\.html$")
OCR_PANEL_PATTERN = re.compile(
    r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
    re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
TEAL = "#1a6b6b"
DEEP_TEAL = "#14524f"  # darker teal for top-level OCR headings, for visual hierarchy
TEXT = "#1a1a2e"
ACCENT = "#c0392b"
FOOTER = "#114b4b"


@dataclass(frozen=True)
class DioceseConfig:
    key: str
    display_name: str
    headline: str
    evidence_path: Path
    pdf_filename: str


@dataclass(frozen=True)
class ViewerEntry:
    diocese: str
    date: str
    path: Path


_FALLBACK_DIOCESES = [
    {
        "key": "derry",
        "display_name": "Derry Diocese",
        "headline": "DERRY DIOCESE COLLATED BULLETIN",
        "evidence_file": "parishes/derry_diocese_bulletin_urls.txt",
        "pdf_filename": "derry_mega_bulletin.pdf",
    },
    {
        "key": "down_and_connor",
        "display_name": "Down & Connor Diocese",
        "headline": "DOWN & CONNOR DIOCESE COLLATED BULLETIN",
        "evidence_file": "parishes/down_and_connor_bulletin_urls.txt",
        "pdf_filename": "down_and_connor_mega_bulletin.pdf",
    },
    {
        "key": "raphoe",
        "display_name": "Raphoe Diocese",
        "headline": "RAPHOE DIOCESE COLLATED BULLETIN",
        "evidence_file": "parishes/raphoe_diocese_bulletin_urls.txt",
        "pdf_filename": "raphoe_mega_bulletin.pdf",
    },
]


def _load_dioceses() -> dict[str, DioceseConfig]:
    config_path = REPO_ROOT / "parishes" / "dioceses.json"
    entries = _FALLBACK_DIOCESES
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data.get("dioceses"), list) and data["dioceses"]:
                entries = data["dioceses"]
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            pass
    result: dict[str, DioceseConfig] = {}
    for entry in entries:
        key = entry["key"]
        result[key] = DioceseConfig(
            key=key,
            display_name=entry["display_name"],
            headline=entry["headline"],
            evidence_path=REPO_ROOT / entry["evidence_file"],
            pdf_filename=entry["pdf_filename"],
        )
    return result


DIOCESES = _load_dioceses()


def parse_parish_links(path: Path) -> list[tuple[str, str]]:
    parish_links: list[tuple[str, str]] = []
    current_name: str | None = None
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        header = HEADER_PATTERN.match(line)
        if header:
            current_name = header.group(1).strip()
            continue
        if not line or line.startswith("#"):
            continue
        if current_name:
            key = re.sub(r"[^a-z0-9]+", "", current_name.lower())
            if key and key not in seen:
                seen.add(key)
                parish_links.append((current_name, line))
            current_name = None
    return parish_links


def extract_ocr_fragment(path: Path) -> str:
    raw_html = path.read_text(encoding="utf-8")
    match = OCR_BODY_PATTERN.search(raw_html)
    if not match:
        raise ValueError(f"Could not find OCR content wrapper in {path}")
    fragment = OCR_PAGE_HEADING_PATTERN.sub(r"<h3>PAGE \1</h3>", match.group(1).strip())
    return tighten_ocr_paragraphs(fragment)


def tighten_ocr_paragraphs(fragment: str) -> str:
    """Merge runs of plain ``<p>…</p>`` into one paragraph with ``<br>`` joins.

    Older OCR HTML put every line in its own ``<p>``, which created huge
    whitespace. New convert_bulletin output already groups lines; this keeps
    legacy fragments readable without a full re-OCR. Also cleans duplicated
    OCR words (ORDINARYORDINARY, word word, 1717th, …).
    """
    from ocr.convert_bulletin import _render_inline

    token_re = re.compile(
        r"(<p>(?!class=)(?![^>]*\bclass=)(.*?)</p>)|(<h[1-6]\b[^>]*>.*?</h[1-6]>|"
        r"<hr\s*/?>|<table\b[\s\S]*?</table>|<p\s+class=\"[^\"]+\">.*?</p>)",
        re.IGNORECASE | re.DOTALL,
    )
    out: list[str] = []
    buf: list[str] = []

    def _clean_inner(inner: str) -> str:
        plain = re.sub(r"<[^>]+>", "", inner or "")
        plain = html.unescape(plain).strip()
        if not plain:
            return ""
        return _render_inline(plain)

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        if len(buf) == 1:
            out.append(f"<p>{buf[0]}</p>")
        else:
            out.append("<p>" + "<br>\n".join(buf) + "</p>")
        buf = []

    pos = 0
    for match in token_re.finditer(fragment):
        if match.start() > pos:
            gap = fragment[pos : match.start()].strip()
            if gap:
                flush()
                out.append(gap)
        if match.group(1) is not None:
            cleaned = _clean_inner(match.group(2) or "")
            if cleaned:
                buf.append(cleaned)
        else:
            flush()
            out.append(match.group(3))
        pos = match.end()
    if pos < len(fragment):
        gap = fragment[pos:].strip()
        if gap:
            flush()
            out.append(gap)
    flush()
    return "\n".join(out) if out else fragment


def count_pdf_pages(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _load_parish_entries(diocese: str, parish_links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    contacts_path = CONTACTS_PATH_BY_DIOCESE.get(diocese)
    display_to_key: dict[str, str] = {}
    if contacts_path and contacts_path.exists():
        try:
            payload = json.loads(contacts_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                parish_key = str(key).strip()
                if not parish_key:
                    continue
                display_to_key[_normalise_name(parish_key)] = parish_key
                if isinstance(value, dict):
                    display_name = str(value.get("display_name") or "").strip()
                    if display_name:
                        display_to_key[_normalise_name(display_name)] = parish_key
                        if display_name.lower().endswith(" parish"):
                            display_to_key[_normalise_name(display_name[:-7])] = parish_key
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, _ in parish_links:
        normalized = _normalise_name(name)
        parish_key = display_to_key.get(normalized) or normalized
        if not parish_key or parish_key in seen:
            continue
        seen.add(parish_key)
        entries.append((parish_key, name))
    return entries


_UI_ARTEFACT_LINE = re.compile(
    r"^(?:parish\s+newsletter(?:\s*[↗→»])?|newsletter(?:\s*[↗→»])?|"
    r"no text this week.*|no searchable text available.*|"
    r"no searchable bulletin text.*|"
    r"page\s+\d+|\d+)$",
    re.IGNORECASE,
)

_SCRAPED_JUNK_LINE = re.compile(
    r"(?i)(?:"
    r"security\s*check|"
    r"before we continue to download|"
    r"i['’]?m a human|"
    r"privacy\s*terms|"
    r"403\s*-?\s*forbidden|"
    r"access to this page is forbidden|"
    r"404\.?\s*that['’]?s an error|"
    r"requested url was not found|"
    r"^not found\.?$|"
    r"parameters you provided were not valid|"
    r"download now and reclaim|"
    r"secure your online searches|"
    r"home\s+webcam\s+sacraments|"
    r"copyright\s*©?\s*20\d{2}|"
    r"all rights reserved|"
    r"^sorry[,!]?\s+the parameters|"
    r"^access denied$"
    r")"
)


def _strip_parish_title_lines(chunk: str, display_name: str, newsletter_url: str) -> str:
    """Remove stitcher banner lines (name + URL) already shown in the section header."""
    from ocr.parish_splitter import _name_patterns, _line_is_parish_marker

    strong, weak = _name_patterns(display_name)
    patterns = strong + weak
    url_norm = (newsletter_url or "").strip().rstrip("/")
    out: list[str] = []
    for line in (chunk or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue
        if _UI_ARTEFACT_LINE.match(stripped):
            continue
        if _SCRAPED_JUNK_LINE.search(stripped):
            continue
        if _line_is_parish_marker(stripped, patterns):
            continue
        compact = stripped.rstrip("/")
        if url_norm:
            left = compact.lower().replace("https://", "").replace("http://", "")
            right = url_norm.lower().replace("https://", "").replace("http://", "")
            if left == right:
                continue
        out.append(line.rstrip())
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _chunk_looks_like_directory(chunk: str) -> bool:
    """True when chunk is mostly the end-of-PDF missing-parish link list."""
    lines = [ln.strip() for ln in (chunk or "").splitlines() if ln.strip()]
    if not lines:
        return True
    if len(lines) <= 2:
        return True
    linkish = 0
    for ln in lines:
        if ln.startswith("http") or ln.endswith(":") or re.fullmatch(r"[A-Za-zÀ-ÿ'’/&\- ]{2,40}", ln.rstrip(":")):
            linkish += 1
    return linkish >= max(2, int(len(lines) * 0.75))


def build_az_parish_ocr_html(
    diocese: str,
    ocr_text: str,
    parish_links: list[tuple[str, str]],
) -> str:
    """Build A–Z parish sections with newsletter URL top-right (new tab)."""
    from ocr.convert_bulletin import render_markdown_lines

    entries = _load_parish_entries(diocese, parish_links)
    if not entries:
        return ""
    url_by_name = {name: url for name, url in parish_links}
    chunks = split_ocr_by_parish(ocr_text or "", entries)
    # split_ocr_by_parish() returns every chunk empty only when it found zero
    # parish-name markers anywhere in the text — i.e. OCR produced nothing
    # usable for the whole diocese, not just one parish having no notice.
    ocr_failed_whole_diocese = bool(entries) and not any(
        (chunks.get(key) or "").strip() for key, _ in entries
    )
    ordered = sorted(entries, key=lambda item: item[1].lower())
    sections: list[str] = []
    if ocr_failed_whole_diocese:
        sections.append(
            '<div class="ocr-failed-banner" role="alert">'
            "⚠️ OCR failed this week — use the original PDF above for the full text."
            "</div>"
        )
    for idx, (parish_key, display_name) in enumerate(ordered):
        url = url_by_name.get(display_name, "")
        raw_chunk = chunks.get(parish_key) or ""
        body_text = _strip_parish_title_lines(raw_chunk, display_name, url)
        if _chunk_looks_like_directory(body_text):
            body_text = ""
        stripe = "even" if idx % 2 == 0 else "odd"
        safe_key = html.escape(parish_key, quote=True)
        safe_name = html.escape(display_name)
        if url:
            safe_href = html.escape(url, quote=True)
            source = (
                f'<a class="parish-source" href="{safe_href}" target="_blank" '
                f'rel="noopener noreferrer" onclick="event.stopPropagation()">Newsletter</a>'
            )
        else:
            source = '<span class="parish-source muted">No newsletter URL</span>'
        if body_text.strip():
            body_html = "\n".join(render_markdown_lines(body_text.splitlines()))
            sections.append(
                f'<details class="parish-block parish-{stripe}" id="parish-{safe_key}">\n'
                f'  <summary class="parish-head">\n'
                f'    <span class="parish-name">{safe_name}</span>\n'
                f"    {source}\n"
                f"  </summary>\n"
                f'  <div class="parish-body">{body_html}</div>\n'
                f"</details>"
            )
        else:
            # Compact single-row empty parish (no tall open accordion).
            sections.append(
                f'<div class="parish-row-empty parish-{stripe}" id="parish-{safe_key}">\n'
                f'  <span class="parish-name">{safe_name}</span>\n'
                f'  <span class="parish-empty">No searchable text available this week.</span>\n'
                f"  {source}\n"
                f"</div>"
            )
    return "\n".join(sections)


_LEGACY_PARISH_DETAILS_RE = re.compile(
    r'<details class="parish-block[^"]*"[^>]*>\s*'
    r'<summary class="parish-head">\s*'
    r'<span class="parish-name">(.*?)</span>.*?'
    r"</summary>\s*"
    r'<div class="parish-body">(.*?)</div>\s*'
    r"</details>",
    re.DOTALL,
)


def _flatten_legacy_parish_accordions(fragment: str) -> str:
    """Backward-compat for already-generated pages.

    Pages regenerated from on-disk HTML (:func:`regenerate_viewer_from_existing`)
    extract their OCR fragment from whatever is already published — which,
    for anything built while the previous (collapsible per-parish
    ``<details>``) design was live, is already wrapped in that accordion
    markup. Flatten any such legacy sections into plain headings so the
    dropdown/collapse behaviour Frank objected to cannot resurface just
    because the source file predates this fix. Fresh OCR conversions never
    contain this markup, so this is a no-op for them.
    """

    def _replace(match: re.Match[str]) -> str:
        name, body = match.group(1), match.group(2)
        return f'<h2 class="b-title">{name}</h2>\n{body}'

    return _LEGACY_PARISH_DETAILS_RE.sub(_replace, fragment or "")


def prepare_ocr_fragment(
    diocese: str,
    ocr_fragment: str,
    parish_links: list[tuple[str, str]] | None = None,
) -> str:
    """Clean OCR HTML into one continuous, page-ordered scrollable document.

    This used to rebuild the text into collapsible per-parish ``<details>``
    accordion sections (see :func:`build_az_parish_ocr_html`, still kept for
    its own tests/possible future use). Frank asked for that dropdown
    behaviour to go — the OCR panel should read exactly like the original
    PDF, page by page, with no per-parish collapse. This keeps the natural
    page order from the OCR pipeline and only prepends a failure banner when
    OCR produced nothing usable at all for any known parish this week.
    """
    cleaned = tighten_ocr_paragraphs(_flatten_legacy_parish_accordions(ocr_fragment or ""))
    if not parish_links:
        return cleaned
    entries = _load_parish_entries(diocese, parish_links)
    if not entries:
        return cleaned
    plain = _fragment_to_plain_text(cleaned)
    chunks = split_ocr_by_parish(plain, entries)
    ocr_failed_whole_diocese = not any((chunks.get(key) or "").strip() for key, _ in entries)
    if not ocr_failed_whole_diocese:
        return cleaned
    banner = (
        '<div class="ocr-failed-banner" role="alert">'
        "⚠️ OCR failed this week — use the original PDF above for the full text."
        "</div>"
    )
    return f"{banner}\n{cleaned}"


def _fragment_to_plain_text(ocr_fragment: str) -> str:
    text = ocr_fragment
    for _ in range(4):
        text = html.unescape(text)
    text = HTML_TAG_PATTERN.sub("\n", text)
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_viewer_plain_text(path: Path) -> str:
    raw_html = path.read_text(encoding="utf-8")
    match = OCR_PANEL_PATTERN.search(raw_html)
    if not match:
        return ""
    return _fragment_to_plain_text(match.group(1))


def _find_previous_viewer_path(diocese: str, bulletin_date: str) -> Path | None:
    try:
        current_date = date.fromisoformat(bulletin_date)
    except ValueError:
        return None
    target = current_date - timedelta(days=7)
    for day_offset in [0, -1, 1, -2, 2, -3, 3]:
        candidate_date = target + timedelta(days=day_offset)
        if candidate_date == current_date:
            continue
        candidate_path = BULLETINS_DIR / f"{diocese}-{candidate_date.isoformat()}.html"
        if candidate_path.exists():
            return candidate_path
    return None


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _update_bulletins_index(base_dir: Path, diocese: str, parish_key: str, last_updated: str) -> None:
    """Atomically update the per-diocese _index.json under *base_dir*."""
    index_path = base_dir / diocese / "_index.json"
    entries: dict[str, str] = {}
    if index_path.exists():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
                entries = raw["entries"]
        except Exception:
            entries = {}
    entries[parish_key] = last_updated
    _write_json(index_path, {"diocese": diocese, "entries": entries})


def _write_parish_reader_outputs(
    diocese: str,
    bulletin_date: str,
    ocr_text: str,
    parish_links: list[tuple[str, str]],
) -> None:
    parish_entries = _load_parish_entries(diocese, parish_links)
    if not parish_entries:
        return

    previous_viewer_path = _find_previous_viewer_path(diocese, bulletin_date)
    if previous_viewer_path:
        previous_text = _read_viewer_plain_text(previous_viewer_path)
        prior_missing = False
    else:
        previous_text = ""
        prior_missing = True

    summaries_disabled = os.getenv("PARISH_AI_SUMMARIES_DISABLE", "").strip() == "1"
    if summaries_disabled:
        print("AI bulletin summaries disabled via PARISH_AI_SUMMARIES_DISABLE=1")

    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    parish_chunks = split_ocr_by_parish(ocr_text, parish_entries)
    previous_chunks = (
        split_ocr_by_parish(previous_text, parish_entries) if previous_text else {}
    )

    for idx, (parish_key, parish_name) in enumerate(parish_entries):
        parish_ocr = parish_chunks.get(parish_key) or ""
        prev_parish_ocr = previous_chunks.get(parish_key) or ""

        if summaries_disabled:
            summary_payload = {"bullets": None, "error": "ai_summaries_disabled"}
        else:
            if idx > 0:
                time.sleep(0.5)
            summary_result = summarise_bulletin(parish_ocr or ocr_text, parish_name, mistral_api_key)
            if summary_result is None:
                missing_api_key = not (mistral_api_key or "").strip()
                if missing_api_key:
                    error_reason = "missing_mistral_api_key"
                else:
                    error_reason = "summary_generation_failed"
                summary_payload = {"bullets": None, "error": error_reason}
            else:
                summary_payload = summary_result

        _write_json(SUMMARIES_DIR / diocese / f"{parish_key}.json", summary_payload)
        _update_bulletins_index(SUMMARIES_DIR, diocese, parish_key, bulletin_date)

        if prior_missing:
            diff_payload = {
                "added_lines": [],
                "removed_lines": [],
                "kept_count": 0,
                "note": "no_prior_bulletin_found",
            }
        else:
            diff_payload = diff_bulletins(parish_ocr or ocr_text, prev_parish_ocr)
        _write_json(DIFFS_DIR / diocese / f"{parish_key}.json", diff_payload)
        _update_bulletins_index(DIFFS_DIR, diocese, parish_key, bulletin_date)

        events = extract_events(parish_ocr or ocr_text, parish_name, parish_key, diocese)
        write_events_json(
            events=events,
            parish_key=parish_key,
            parish_name=parish_name,
            diocese=diocese,
            bulletin_date=bulletin_date,
            ai_provider=None,
            error=None,
            repo_root=REPO_ROOT,
        )

def render_parish_link_grid(parish_links: list[tuple[str, str]]) -> str:
    """Searchable A–Z parish link grid — shared by every canonical viewer page."""
    if not parish_links:
        return '<p class="empty-state">No parish bulletin links were found for this diocese yet.</p>'
    sorted_links = sorted(parish_links, key=lambda pair: pair[0].lower())
    items = []
    seen: set[str] = set()
    for name, url in sorted_links:
        key = _normalise_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(
            (
                "<li class=\"parish-item\" data-name=\"{name_key}\">"
                "<a class=\"parish-link\" href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">"
                "<span aria-hidden=\"true\">⛪</span> <span>{name}</span></a></li>"
            ).format(
                name_key=html.escape(name.lower(), quote=True),
                url=html.escape(url, quote=True),
                name=html.escape(name),
            )
        )
    return (
        '<div id="parish-empty" class="empty-state" hidden>No matching parishes found.</div>'
        f'<ul id="parish-grid" class="parish-grid">{"".join(items)}</ul>'
    )


def _diocese_label(display_name: str) -> str:
    return display_name.replace(" Diocese", "").upper()


def format_uk_date(iso_date: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso_date or "").strip())
    if not match:
        return str(iso_date or "").strip()
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"


def render_ocr_standalone_page(
    config: DioceseConfig,
    bulletin_date: str,
    ocr_fragment: str,
    viewer_href: str,
) -> str:
    """Mobile-friendly OCR-only page for opening bulletin text in a new tab."""
    diocese_label = _diocese_label(config.display_name)
    uk_bulletin_date = format_uk_date(bulletin_date)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5" />
  <title>{html.escape(config.display_name)} Text Bulletin — {html.escape(uk_bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Georgia, "Times New Roman", Times, serif;
      background: #fff;
      color: {TEXT};
      line-height: 1.35;
      font-size: 1.05rem;
      -webkit-text-size-adjust: 100%;
    }}
    a {{ color: #1d4ed8; text-decoration: underline; font-weight: 600; }}
    .page {{ max-width: 100%; margin: 0; padding: 8px 10px 24px; }}
    .top {{
      display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
      gap: 8px 14px;
      margin-bottom: 8px; font-family: Georgia, "Times New Roman", Times, serif;
    }}
    .top-left {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 14px; }}
    .back-link {{
      font-family: system-ui, sans-serif; font-size: 0.85rem; font-weight: 700;
      color: #1e3a5f; text-decoration: none;
    }}
    .title-line {{
      font-size: 1.05rem; font-weight: 700; color: {TEXT};
    }}
    .font-size-controls {{ display: none; }}
    .ocr-zoom-bar {{
      position: sticky; top: 0; z-index: 6;
      display: flex; justify-content: center; align-items: center; gap: 6px;
      margin: 0 0 6px; padding: 4px 8px;
      background: #f8fafc;
      border: 1px solid #e5e7eb; border-radius: 6px;
      font-family: system-ui, sans-serif;
    }}
    .ocr-zoom-bar button {{
      min-width: 32px; min-height: 32px; border: 1px solid #1e3a5f; border-radius: 4px;
      background: #fff; color: #1e3a5f; font-weight: 700; font-size: 1rem; cursor: pointer;
      line-height: 1;
    }}
    .ocr-zoom-pct {{
      min-width: 3rem; text-align: center; font-weight: 700; font-size: 0.85rem; color: #1e3a5f;
    }}
    .ocr-zoom-hint {{ display: none; font-size: 0.7rem; color: #666666; }}
    @media (pointer: coarse) {{ .ocr-zoom-hint {{ display: inline; margin-left: 4px; }} }}
    .ocr-body {{
      background: #fff;
      padding: 0 2px;
      max-width: 100%;
      font-size: calc(1.05rem * var(--ocr-scale, 1));
      touch-action: pan-x pan-y pinch-zoom;
      color: #222222;
    }}
    .ocr-body h1, .ocr-body h2 {{ color: {DEEP_TEAL}; margin: 0.7em 0 0.2em; font-weight: 700; font-size: 1.15em; }}
    .ocr-body h3, .ocr-body h4 {{ color: {TEAL}; margin: 0.6em 0 0.15em; font-weight: 700; }}
    .ocr-body h2.b-title, .ocr-body .b-title {{
      font-size: 1.2em; border-bottom: 1px solid #c8d6f0; padding-bottom: 0.1em;
    }}
    .ocr-body h3.ocr-page-heading, .ocr-body .page-label {{
      font-size: 0.72rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin: 0.85em 0 0.25em;
      font-family: system-ui, sans-serif;
      color: #64748b;
    }}
    .ocr-body p {{ margin: 0 0 0.35em; }}
    .ocr-body hr {{ border: 0; border-top: 1px solid #e2e8f0; margin: 0.7em 0; }}
    .ocr-body mark {{ background: #fff3cd; padding: 0 2px; border-radius: 2px; }}
    .ocr-body mark.search-active {{ background: #fde047; outline: 2px solid #0f5e5e; }}
    .parish-block {{
      margin: 0 0 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      background: #fff;
    }}
    .parish-block.parish-odd {{ background: #f7faf9; }}
    .parish-block > summary.parish-head {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 6px 12px;
      margin: 0;
      padding: 0.4rem 0.55rem 0.4rem 0.6rem;
      border-left: 3px solid {TEAL};
      cursor: pointer;
      list-style: none;
    }}
    .parish-block > summary.parish-head::-webkit-details-marker {{ display: none; }}
    .parish-odd > summary.parish-head {{ border-left-color: {DEEP_TEAL}; }}
    .parish-name {{
      margin: 0 !important;
      font-size: 1.08rem !important;
      font-family: Georgia, "Times New Roman", Times, serif;
      color: {DEEP_TEAL} !important;
      border: 0 !important;
      padding: 0 !important;
      font-weight: 700;
    }}
    .parish-name::before {{
      content: "▸ ";
      color: {TEAL};
      font-family: system-ui, sans-serif;
      font-size: 0.85em;
    }}
    .parish-block[open] .parish-name::before {{ content: "▾ "; }}
    .parish-source {{
      font-family: system-ui, sans-serif;
      font-size: 0.78rem;
      font-weight: 600;
      white-space: nowrap;
      text-decoration: none !important;
      color: #1d4ed8;
    }}
    .parish-source:hover {{ text-decoration: underline !important; }}
    .parish-source.muted {{ color: #94a3b8; font-weight: 500; }}
    .parish-body {{ padding: 0.2rem 0.6rem 0.65rem; }}
    .parish-empty {{
      font-family: system-ui, sans-serif;
      font-size: 16px;
      color: #666666;
      font-style: normal;
      font-weight: 400;
    }}
    .parish-row-empty {{
      display: flex;
      flex-wrap: nowrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px 12px;
      min-height: 48px;
      height: auto;
      max-height: 64px;
      padding: 8px 0;
      margin: 0;
      border: 0;
      border-bottom: 1px solid #e5e7eb;
      background: transparent;
      box-sizing: border-box;
    }}
    .parish-row-empty .parish-name {{
      margin: 0 !important;
      font-size: 16px !important;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif !important;
      color: #1e3a5f !important;
      font-weight: 600;
      flex: 0 1 auto;
    }}
    .parish-row-empty .parish-name::before {{ content: none !important; }}
    .parish-row-empty .parish-empty {{
      flex: 1 1 auto;
      margin: 0;
      color: #666666;
      font-size: 16px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .parish-row-empty .parish-source {{
      color: #1e3a5f;
      font-size: 16px;
      flex: 0 0 auto;
    }}
    .search-panel {{
      margin: 0 0 8px;
      font-family: system-ui, sans-serif;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 6px 8px;
      background: #f8fafc;
    }}
    .search-panel .ocr-search-bar {{ margin-bottom: 4px; }}
    .ocr-search-bar {{ position: relative; margin-bottom: 4px; }}
    .search-input {{
      width: 100%; min-height: 34px; border: 1px solid #e5e7eb; border-radius: 5px;
      padding: 5px 30px 5px 10px; font-size: 0.92rem;
      font-family: system-ui, sans-serif; color: #222222; background: #fff;
    }}
    .search-clear {{ position: absolute; right: 4px; top: 50%; transform: translateY(-50%); width: 26px; height: 26px; border: 0; background: transparent; color: #666666; font-size: 1rem; cursor: pointer; }}
    .search-clear[hidden] {{ display: none; }}
    .ocr-search-tools {{
      display: flex; align-items: center; justify-content: space-between; gap: 8px;
      flex-wrap: wrap;
    }}
    .ocr-search-tools button {{
      border: 1px solid #1e3a5f; border-radius: 4px; background: #fff; color: #1e3a5f;
      font-weight: 600; min-height: 30px; padding: 3px 10px; cursor: pointer; font-size: 0.8rem;
    }}
    .ocr-search-tools button:disabled {{ color: #999; border-color: #e5e7eb; cursor: not-allowed; }}
    .match-count {{ color: #666666; font-size: 0.78rem; font-weight: 600; }}
    .note-box {{
      margin-top: 10px;
      color: #666666;
      font-weight: 400;
      font-size: 13px;
      line-height: 1.35;
      font-family: system-ui, sans-serif;
      font-style: normal;
      padding: 0;
    }}
    .ocr-failed-banner {{
      margin: 10px 0;
      padding: 10px 14px;
      background: #fff4df;
      border: 1px solid #f5d08d;
      border-radius: 6px;
      color: #713f12;
      font-weight: 600;
      font-size: 13px;
    }}
    body.embed-mode .top {{ display: none !important; }}
    body.embed-mode .page {{ padding-top: 4px; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="top" id="ocr-top">
      <div class="top-left">
        <a class="back-link" href="{html.escape(viewer_href, quote=True)}">← Viewer</a>
        <span class="title-line">{html.escape(diocese_label)} Text Bulletin · {html.escape(uk_bulletin_date)}</span>
      </div>
    </div>
    <div class="ocr-zoom-bar" role="group" aria-label="Text zoom">
      <button type="button" data-ocr-zoom="-1" aria-label="Zoom out">−</button>
      <span class="ocr-zoom-pct" id="ocr-zoom-pct">100%</span>
      <button type="button" data-ocr-zoom="1" aria-label="Zoom in">+</button>
      <span class="ocr-zoom-hint">or pinch to zoom</span>
    </div>
    <div class="search-panel" role="search">
      <div class="ocr-search-bar">
        <input id="ocr-search" class="search-input" type="search" placeholder="Search text (mass, bingo, parish…)" aria-label="Search bulletin text" />
        <button id="clear-search" class="search-clear" type="button" aria-label="Clear search" hidden>×</button>
      </div>
      <div class="ocr-search-tools">
        <span id="ocr-match-count" class="match-count">0 matches</span>
        <div>
          <button id="ocr-prev" type="button" disabled>← Prev</button>
          <button id="ocr-next" type="button" disabled>Next →</button>
        </div>
      </div>
    </div>
    <div class="ocr-body" id="ocr-text">{ocr_fragment}</div>
    <p class="note-box">Auto-generated from the bulletin PDF. Irish (Gaeilge) and English preserved as printed. Check mass times and names against the original PDF.</p>
  </div>
  <script>
    (function () {{
      try {{
        if (new URLSearchParams(window.location.search).get('embed') === '1') {{
          document.body.classList.add('embed-mode');
        }}
      }} catch (e) {{}}
    }})();
    (function () {{
      var KEY = 'ph_ocr_scale';
      var percents = [75, 85, 100, 115, 130, 150, 175, 200];
      var root = document.getElementById('ocr-text');
      var label = document.getElementById('ocr-zoom-pct');
      if (!root) return;
      function apply(pct) {{
        root.style.setProperty('--ocr-scale', String(pct / 100));
        if (label) label.textContent = pct + '%';
        try {{ localStorage.setItem(KEY, String(pct)); }} catch (e) {{}}
      }}
      var saved = 100;
      try {{
        var raw = localStorage.getItem(KEY);
        if (raw) {{
          var n = parseFloat(raw);
          if (n > 0 && n < 3) saved = Math.round(n * 100);
          else if (n >= 50 && n <= 250) saved = Math.round(n);
        }}
      }} catch (e) {{}}
      if (percents.indexOf(saved) < 0) {{
        saved = percents.reduce(function (best, p) {{
          return Math.abs(p - saved) < Math.abs(best - saved) ? p : best;
        }}, 100);
      }}
      apply(saved);
      document.querySelectorAll('[data-ocr-zoom]').forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          var dir = parseInt(btn.getAttribute('data-ocr-zoom'), 10) || 0;
          var idx = percents.indexOf(saved);
          if (idx < 0) idx = percents.indexOf(100);
          idx = Math.max(0, Math.min(percents.length - 1, idx + dir));
          saved = percents[idx];
          apply(saved);
        }});
      }});
    }})();
    (function () {{
      const ocrRoot = document.getElementById('ocr-text');
      const ocrSearch = document.getElementById('ocr-search');
      const clearSearch = document.getElementById('clear-search');
      const matchCount = document.getElementById('ocr-match-count');
      const prevMatchBtn = document.getElementById('ocr-prev');
      const nextMatchBtn = document.getElementById('ocr-next');
      if (!ocrRoot || !ocrSearch) return;
      const originalHtml = ocrRoot.innerHTML;
      let ocrMatches = [];
      let currentMatchIndex = -1;
      function escapeRegExp(text) {{
        return text.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
      }}
      function scrollToMatch(idx) {{
        if (!ocrMatches.length || idx < 0 || idx >= ocrMatches.length) return;
        ocrMatches.forEach((mark) => mark.classList.remove('search-active'));
        ocrMatches[idx].classList.add('search-active');
        ocrMatches[idx].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}
      function updateMatchUi() {{
        const total = ocrMatches.length;
        if (!total) {{
          matchCount.textContent = '0 matches';
          prevMatchBtn.disabled = true;
          nextMatchBtn.disabled = true;
          return;
        }}
        matchCount.textContent = `${{currentMatchIndex + 1}} of ${{total}} matches`;
        prevMatchBtn.disabled = false;
        nextMatchBtn.disabled = false;
      }}
      function applySearch(query) {{
        ocrRoot.innerHTML = originalHtml;
        ocrMatches = [];
        currentMatchIndex = -1;
        if (!query) {{
          clearSearch.hidden = true;
          updateMatchUi();
          return;
        }}
        clearSearch.hidden = false;
        const regex = new RegExp(escapeRegExp(query), 'gi');
        const walker = document.createTreeWalker(ocrRoot, NodeFilter.SHOW_TEXT, null);
        const nodes = [];
        while (walker.nextNode()) {{
          const node = walker.currentNode;
          if (node.parentElement && node.parentElement.tagName !== 'MARK' && node.nodeValue.trim()) nodes.push(node);
        }}
        nodes.forEach((node) => {{
          const text = node.nodeValue;
          regex.lastIndex = 0;
          if (!regex.test(text)) return;
          regex.lastIndex = 0;
          const fragment = document.createDocumentFragment();
          let lastIndex = 0;
          let match;
          while ((match = regex.exec(text)) !== null) {{
            if (match.index > lastIndex) fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
            const mark = document.createElement('mark');
            mark.textContent = match[0];
            fragment.appendChild(mark);
            ocrMatches.push(mark);
            lastIndex = match.index + match[0].length;
          }}
          if (lastIndex < text.length) fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
          node.parentNode.replaceChild(fragment, node);
        }});
        ocrRoot.querySelectorAll('details.parish-block').forEach((details) => {{
          details.open = Boolean(details.querySelector('mark'));
        }});
        if (ocrMatches.length) {{
          currentMatchIndex = 0;
          scrollToMatch(currentMatchIndex);
        }}
        updateMatchUi();
      }}
      ocrSearch.addEventListener('input', (e) => applySearch(e.target.value.trim()));
      clearSearch.addEventListener('click', () => {{ ocrSearch.value = ''; applySearch(''); ocrSearch.focus(); }});
      prevMatchBtn.addEventListener('click', () => {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex - 1 + ocrMatches.length) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});
      nextMatchBtn.addEventListener('click', () => {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex + 1) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});
      ocrSearch.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter' && ocrMatches.length) {{
          e.preventDefault();
          currentMatchIndex = (currentMatchIndex + 1) % ocrMatches.length;
          updateMatchUi();
          scrollToMatch(currentMatchIndex);
        }}
      }});
    }})();
  </script>
</body>
</html>
"""


def _pdf_href(config: DioceseConfig) -> str:
    return f"../mega_pdf/{config.pdf_filename}"


def _ocr_standalone_href(config: DioceseConfig, bulletin_date: str) -> str:
    return f"{config.key}-{bulletin_date}-ocr.html"


def _pdf_standalone_href(config: DioceseConfig, bulletin_date: str) -> str:
    return f"{config.key}-{bulletin_date}-pdf.html"


def render_viewer_page(config: DioceseConfig, bulletin_date: str, page_count: int, ocr_fragment: str, parish_links: list[tuple[str, str]]) -> str:
    """Dated bulletin-archive viewer page (docs/bulletins/{diocese}-{date}.html).

    Thin wrapper around :func:`render_bulletin_viewer_shell`, the single
    canonical viewer design shared with the per-diocese "current" pages
    rendered by ``harvester.page_renderer.render_diocese_raphoe_page``.
    """
    diocese_label = _diocese_label(config.display_name)
    uk_bulletin_date = format_uk_date(bulletin_date)
    return render_bulletin_viewer_shell(
        page_title=f"{config.display_name} Bulletin Viewer — {uk_bulletin_date}",
        diocese_label=diocese_label,
        display_name=config.display_name,
        headline=config.headline.replace("DIOCESE ", "").replace("BIG BULLETIN", "COLLATED BULLETIN"),
        meta_line=f"Generated for {uk_bulletin_date}.",
        back_href="index.html",
        back_label="← Back to bulletin archive",
        pdf_href=_pdf_href(config),
        pdf_download_href=_pdf_href(config),
        pdf_standalone_href=_pdf_standalone_href(config, bulletin_date),
        ocr_standalone_href=_ocr_standalone_href(config, bulletin_date),
        ocr_fragment=ocr_fragment,
        parish_section_heading=f"{diocese_label} Parishes with Working Bulletin Links",
        parish_links_html=render_parish_link_grid(parish_links),
    )


def render_pdf_standalone_page(config: DioceseConfig, bulletin_date: str, pdf_href: str, viewer_href: str) -> str:
    """Distraction-free, chrome-free full-page PDF view — mirrors render_ocr_standalone_page."""
    diocese_label = _diocese_label(config.display_name)
    uk_bulletin_date = format_uk_date(bulletin_date)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} PDF — {html.escape(uk_bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #525659;
      color: {TEXT};
      display: flex;
      flex-direction: column;
    }}
    .top {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px 14px;
      padding: 8px 12px;
      background: #fff;
      border-bottom: 1px solid #d6ecea;
    }}
    .top-left {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 14px; }}
    .back-link {{ font-weight: 700; color: {TEAL}; text-decoration: none; font-size: 0.9rem; }}
    .title-line {{ font-weight: 700; font-size: 0.9rem; color: {TEXT}; }}
    .download-link {{ font-weight: 700; color: {TEAL}; text-decoration: none; font-size: 0.85rem; white-space: nowrap; }}
    .pdf-frame {{ flex: 1 1 auto; border: 0; width: 100%; height: 100%; background: #525659; }}
    body.embed-mode .top {{ display: none !important; }}
  </style>
</head>
<body>
  <div class="top" id="pdf-top">
    <div class="top-left">
      <a class="back-link" href="{html.escape(viewer_href, quote=True)}">← Viewer</a>
      <span class="title-line">{html.escape(diocese_label)} · {html.escape(uk_bulletin_date)}</span>
    </div>
    <a class="download-link" href="{html.escape(pdf_href, quote=True)}" download>⬇ Download PDF</a>
  </div>
  <iframe class="pdf-frame" src="{html.escape(pdf_href, quote=True)}" title="{html.escape(config.display_name)} bulletin PDF"></iframe>
  <script>
    (function () {{
      try {{
        if (new URLSearchParams(window.location.search).get('embed') === '1') {{
          document.body.classList.add('embed-mode');
        }}
      }} catch (e) {{}}
    }})();
  </script>
</body>
</html>
"""


def render_bulletin_viewer_shell(
    *,
    page_title: str,
    diocese_label: str,
    display_name: str,
    headline: str,
    meta_line: str,
    back_href: str,
    back_label: str,
    pdf_href: str,
    pdf_download_href: str,
    pdf_standalone_href: str,
    ocr_standalone_href: str,
    ocr_fragment: str,
    parish_section_heading: str,
    parish_links_html: str,
) -> str:
    """The single canonical PDF + Text Bulletin viewer design for this project.

    Used for both the dated bulletin-archive pages
    (``docs/bulletins/{diocese}-{date}.html``, via :func:`render_viewer_page`)
    and the per-diocese "current" pages
    (``docs/dioceses/{key}/index.html``, via
    ``harvester.page_renderer.render_diocese_raphoe_page``) so Raphoe, Derry
    and Down & Connor always share one visual/structural design.

    Matches the flat, single-column layout Frank's own reference page uses:
    headline -> plain "Download PDF" link -> "Original PDF Version" heading
    -> PDF viewer (always visible, not behind a tab) -> a find-text-instantly
    callout -> "OCR Extracted Plain Text" heading -> one continuous,
    page-ordered OCR panel (no per-parish accordion/dropdown) -> the A-Z
    parish link grid, all on this one page. Includes a genuine
    distraction-free full-page mode for both the PDF (``pdf_standalone_href``)
    and the OCR text (``ocr_standalone_href``), each surfaced as an
    "open in new tab" toolbar link.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5" />
  <title>{html.escape(page_title)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #fafbfc;
      color: {TEXT};
      line-height: 1.55;
    }}
    a {{ color: {TEAL}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{ max-width: 1100px; margin: 0 auto; padding: 16px 16px 40px; }}
    .back-link {{ display: inline-block; margin-bottom: 14px; font-weight: 700; color: {TEAL}; }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .diocese-label {{ margin: 0 0 6px; color: {ACCENT}; font-size: 0.95rem; letter-spacing: 0.15em; text-transform: uppercase; font-weight: 800; }}
    h1 {{ margin: 0 0 8px; color: {TEAL}; font-size: clamp(1.8rem, 3vw, 2.5rem); }}
    .meta {{ color: #6b7280; font-size: 0.95rem; }}
    
    /* Top download link — plain, prominent, right under the headline */
    .download-link-top {{
      display: inline-block;
      margin-top: 4px;
      font-weight: 700;
      font-size: 1rem;
      color: {TEAL};
    }}

    /* Section headings — "BULLETIN — ORIGINAL PDF VERSION" style dividers
       between the always-visible PDF and OCR panels below (no tabs). */
    .section-heading {{
      margin: 30px 0 14px;
      text-align: center;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 800;
      font-size: 1.05rem;
      color: {DEEP_TEAL};
    }}

    /* Pro-tip callout between the PDF and OCR sections */
    .callout-tip {{
      margin: 18px auto;
      max-width: 720px;
      text-align: center;
      background: #fff4df;
      border: 1px solid #f5c451;
      border-radius: 999px;
      padding: 10px 22px;
      color: #7a4a00;
      font-size: 0.92rem;
      font-weight: 600;
    }}
    .callout-tip strong {{ font-weight: 800; }}

    /* Viewer blocks — PDF and OCR are both always visible, stacked, no tabs */
    .viewer-block {{
      background: white;
      border: 1px solid #d6ecea;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 4px 12px rgba(26, 107, 107, 0.08);
      margin-bottom: 8px;
    }}
    
    /* Toolbar */
    .panel-toolbar {{
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .toolbar-btn {{
      padding: 8px 16px;
      border: 2px solid {TEAL};
      border-radius: 6px;
      background: white;
      color: {TEAL};
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .toolbar-btn:hover {{
      background: {TEAL};
      color: white;
      text-decoration: none;
    }}
    
    /* PDF View — the browser's own PDF viewer supplies page number, zoom
       and print/download controls inside the iframe; we only add a small
       fullscreen shortcut on top of it. */
    .pdf-frame-wrap {{
      position: relative;
      height: 92vh;
      min-height: 92vh;
      overflow: hidden;
      border: 1px solid #c7dcda;
      border-radius: 10px;
      background: #f2f5f5;
    }}
    .pdf-frame-wrap iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      display: block;
    }}
    .fullscreen-btn {{
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 5;
      width: 36px;
      height: 36px;
      border: 1px solid {TEAL};
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.92);
      color: {TEAL};
      font-size: 1.1rem;
      line-height: 1;
      cursor: pointer;
    }}
    .fullscreen-btn:hover {{ background: #fff; }}
    .ocr-search-bar {{
      position: relative;
      margin-bottom: 12px;
    }}
    .search-input {{
      width: 100%;
      border: 1px solid #bdd7d5;
      border-radius: 8px;
      padding: 12px 44px 12px 16px;
      font-size: 1rem;
    }}
    .search-clear {{
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      width: 32px;
      height: 32px;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: #6b7280;
      font-size: 1.3rem;
      cursor: pointer;
    }}
    .search-clear[hidden] {{ display: none; }}
    .ocr-search-tools {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .ocr-search-tools button {{
      border: 0;
      border-radius: 6px;
      background: {TEAL};
      color: white;
      font-weight: 600;
      padding: 7px 14px;
      cursor: pointer;
      font-size: 0.9rem;
    }}
    .ocr-search-tools button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    .match-count {{
      color: #6b7280;
      font-size: 0.9rem;
      font-weight: 600;
    }}
    .font-size-controls {{ display: none; }}
    .ocr-zoom-bar {{
      position: sticky; top: 0; z-index: 6;
      display: flex; justify-content: center; align-items: center; gap: 10px;
      margin: 0 0 10px; padding: 6px 10px;
      background: rgba(248, 250, 250, 0.97);
      border: 1px solid #e2e8f0; border-radius: 6px;
    }}
    .ocr-zoom-bar button {{
      min-width: 40px; min-height: 40px; border: 1px solid {TEAL}; border-radius: 4px;
      background: #fff; color: {TEAL}; font-weight: 700; font-size: 1.15rem; cursor: pointer;
    }}
    .ocr-zoom-pct {{
      min-width: 3.5rem; text-align: center; font-weight: 700; font-size: 0.95rem; color: {DEEP_TEAL};
    }}
    .ocr-zoom-hint {{ display: none; font-size: 0.72rem; color: #64748b; }}
    @media (pointer: coarse) {{ .ocr-zoom-hint {{ display: inline; margin-left: 6px; }} }}
    #ocr-panel {{
      height: 92vh;
      min-height: 92vh;
      overflow-y: auto;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 14px 16px 22px;
      background: white;
      font-family: Georgia, "Times New Roman", Times, serif;
      font-size: calc(1.08rem * var(--ocr-scale, 1));
      line-height: 1.38;
      color: {TEXT};
      max-width: min(52rem, 100%);
      margin: 0 auto;
      touch-action: pan-x pan-y pinch-zoom;
    }}
    #ocr-panel h1, #ocr-panel h2 {{
      color: {DEEP_TEAL};
      margin-top: 0.9em;
      margin-bottom: 0.3em;
      font-weight: 700;
    }}
    #ocr-panel h2.b-title {{
      font-size: 1.28em;
      color: #0f2b5b;
      border-bottom: 2px solid #c8d6f0;
      padding-bottom: 0.12em;
    }}
    #ocr-panel h3.b-head {{
      font-size: 1.12em;
      color: #134e9c;
    }}
    #ocr-panel h4.b-sub {{
      font-size: 1.02em;
      color: #1f6f4a;
    }}
    #ocr-panel h3, #ocr-panel h4 {{
      color: {TEAL};
      margin-top: 0.8em;
      margin-bottom: 0.25em;
      font-weight: 700;
    }}
    #ocr-panel .page-label {{
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin: 1.1em 0 0.35em;
      color: #64748b;
      font-family: system-ui, sans-serif;
    }}
    #ocr-panel table.b-table {{
      border-collapse: collapse;
      width: 100%;
      margin: 0.45em 0 0.75em;
      font-size: 0.95em;
    }}
    #ocr-panel table.b-table td, #ocr-panel table.b-table th {{
      border: 1px solid #d0d8e8;
      padding: 4px 8px;
      text-align: left;
      vertical-align: top;
    }}
    #ocr-panel table.b-table th {{
      background: #eef3fb;
      color: #0f2b5b;
    }}
    #ocr-panel table.b-table tr:nth-child(even) td {{
      background: #f7f9fd;
    }}
    #ocr-panel hr {{ border: 0; border-top: 1px solid #e2e8f0; margin: 0.9em 0; }}
    #ocr-panel p {{ margin: 0 0 0.35em; }}
    #ocr-panel mark {{ background: #fef08a; padding: 1px 3px; border-radius: 2px; }}
    #ocr-panel mark.search-active {{ background: #fde047; outline: 2px solid #0f5e5e; }}
    #ocr-panel a {{ color: {TEAL}; font-weight: 600; }}
    #ocr-panel .parish-block {{
      margin: 0 0 0.5rem;
      padding: 0;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      background: #fff;
    }}
    #ocr-panel .parish-block.parish-odd {{ background: #f7faf9; }}
    #ocr-panel .parish-block > summary.parish-head {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 6px 12px;
      margin: 0;
      padding: 0.4rem 0.55rem;
      border-left: 3px solid {TEAL};
      cursor: pointer;
      list-style: none;
    }}
    #ocr-panel .parish-block > summary.parish-head::-webkit-details-marker {{ display: none; }}
    #ocr-panel .parish-odd > summary.parish-head {{ border-left-color: {DEEP_TEAL}; }}
    #ocr-panel .parish-name {{
      margin: 0 !important;
      font-size: 1.1rem !important;
      color: {DEEP_TEAL} !important;
      border: 0 !important;
      padding: 0 !important;
      font-weight: 700;
    }}
    #ocr-panel .parish-name::before {{
      content: "▸ ";
      color: {TEAL};
      font-family: system-ui, sans-serif;
      font-size: 0.85em;
    }}
    #ocr-panel .parish-block[open] .parish-name::before {{ content: "▾ "; }}
    #ocr-panel .parish-source {{
      font-family: system-ui, sans-serif;
      font-size: 0.78rem;
      font-weight: 600;
      white-space: nowrap;
      text-decoration: none;
      color: #1d4ed8;
    }}
    #ocr-panel .parish-source:hover {{ text-decoration: underline; }}
    #ocr-panel .parish-body {{ padding: 0.25rem 0.55rem 0.65rem; }}
    #ocr-panel .parish-empty {{
      font-family: system-ui, sans-serif;
      font-size: 16px;
      color: #666666;
      font-style: normal;
    }}
    #ocr-panel .parish-row-empty {{
      display: flex;
      flex-wrap: nowrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px 12px;
      min-height: 48px;
      max-height: 64px;
      padding: 8px 0;
      margin: 0;
      border: 0;
      border-bottom: 1px solid #e5e7eb;
      background: transparent;
      box-sizing: border-box;
    }}
    #ocr-panel .parish-row-empty .parish-name {{
      margin: 0 !important;
      font-size: 16px !important;
      font-family: system-ui, sans-serif !important;
      color: #1e3a5f !important;
      font-weight: 600;
    }}
    #ocr-panel .parish-row-empty .parish-name::before {{ content: none !important; }}
    #ocr-panel .parish-row-empty .parish-empty {{
      flex: 1 1 auto;
      margin: 0;
      color: #666666;
      font-size: 16px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    #ocr-panel .parish-row-empty .parish-source {{ color: #1e3a5f; font-size: 16px; }}
    .note-box {{
      margin-top: 12px;
      padding: 6px 0;
      border-radius: 0;
      background: transparent;
      border: 0;
      color: #666666;
      font-weight: 400;
      font-size: 13px;
    }}
    .ocr-failed-banner {{
      margin: 10px 0;
      padding: 10px 14px;
      background: #fff4df;
      border: 1px solid #f5d08d;
      border-radius: 6px;
      color: #713f12;
      font-weight: 600;
      font-size: 13px;
    }}
    .empty-state[hidden],
    #parish-empty[hidden] {{ display: none !important; }}
    .parish-section {{
      margin-top: 28px;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      padding: 16px;
    }}
    .parish-section h2.section-heading {{
      color: #1e3a5f;
      font-size: 1.2rem;
    }}
    .parish-filter {{
      width: 100%;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 10px 12px;
      font-size: 0.95rem;
      margin-bottom: 12px;
    }}
    ul.parish-grid {{
      list-style: none;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      padding: 0;
      margin: 0;
    }}
    .parish-item {{ margin: 0; }}
    .parish-link {{
      min-height: 48px;
      display: flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      color: {TEAL};
      font-size: 1rem;
      font-weight: 700;
      background: #f9fcfc;
      border: 1px solid #d9ecea;
      border-radius: 8px;
      padding: 10px 14px;
      transition: all 0.15s;
    }}
    .parish-link:hover {{
      background: #e8f4f4;
      text-decoration: none;
      transform: translateY(-1px);
    }}
    .empty-state {{ margin: 0 0 12px; color: #6b7280; font-size: 0.95rem; }}
    
    /* Footer */
    footer {{
      margin-top: 32px;
      background: {FOOTER};
      color: white;
      padding: 16px 20px;
    }}
    .footer-inner {{
      max-width: 1100px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      font-size: 0.9rem;
    }}
    .footer-inner a {{ color: #d8f0ee; font-weight: 700; }}
    .footer-inner a:hover {{ text-decoration: underline; }}
    
    /* Responsive */
    @media (max-width: 900px) {{
      ul.parish-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 600px) {{
      .page {{ padding: 16px 12px; }}
      ul.parish-grid {{ grid-template-columns: 1fr; }}
      .pdf-frame-wrap, #ocr-panel {{
        height: 90vh;
        min-height: 90vh;
      }}
      .ocr-search-tools {{ flex-direction: column; }}
      .ocr-search-tools button {{
        min-height: 48px;
        width: 100%;
      }}
      .panel-toolbar {{ justify-content: stretch; }}
      .toolbar-btn {{ flex: 1; justify-content: center; min-height: 48px; }}
      .callout-tip {{ margin-left: 8px; margin-right: 8px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{html.escape(back_href, quote=True)}">{html.escape(back_label)}</a>
    <header class="header">
      <p class="diocese-label">{html.escape(diocese_label)}</p>
      <h1>{html.escape(headline)}</h1>
      <p class="meta">{html.escape(meta_line)}</p>
      <a class="download-link-top" href="{html.escape(pdf_download_href, quote=True)}" download>⬇ Download PDF</a>
    </header>

    <!-- PDF section: always visible (no tab click needed), original PDF first -->
    <h2 class="section-heading">Bulletin — Original PDF Version</h2>
    <div id="panel-pdf" class="viewer-block">
      <div class="panel-toolbar">
        <a class="toolbar-btn" href="{html.escape(pdf_href, quote=True)}" target="_blank" rel="noopener noreferrer">↗ Open PDF in new tab</a>
        <a class="toolbar-btn" href="{html.escape(pdf_standalone_href, quote=True)}" target="_blank" rel="noopener noreferrer">🖥 Distraction-free view</a>
        <a class="toolbar-btn" href="{html.escape(pdf_download_href, quote=True)}" download>⬇ Download PDF</a>
      </div>
      <div class="pdf-frame-wrap" id="pdf-frame-wrap">
        <button type="button" class="fullscreen-btn" id="pdf-fullscreen-btn" aria-label="View PDF fullscreen" title="View fullscreen">⛶</button>
        <iframe src="{html.escape(pdf_href, quote=True)}" title="{html.escape(display_name)} bulletin PDF"></iframe>
      </div>
    </div>

    <p class="callout-tip">🔍 <strong>Pro tip: find text instantly.</strong> Use the search box below (or your browser's Ctrl/Cmd+F) to jump straight to a parish, name or notice in the text version underneath.</p>

    <!-- OCR section: one continuous, page-ordered document — no per-parish
         dropdown/accordion. Reads exactly like the PDF, just as searchable
         text. -->
    <h2 class="section-heading">Bulletin — OCR Extracted Plain Text</h2>
    <div id="panel-ocr" class="viewer-block">
      <div class="panel-toolbar">
        <a class="toolbar-btn" href="{html.escape(ocr_standalone_href, quote=True)}" target="_blank" rel="noopener noreferrer">↗ Open bulletin text in new tab (distraction-free)</a>
      </div>
      <div class="ocr-zoom-bar" role="group" aria-label="Text zoom">
        <button type="button" data-ocr-zoom="-1" aria-label="Zoom out">−</button>
        <span class="ocr-zoom-pct" id="ocr-zoom-pct">100%</span>
        <button type="button" data-ocr-zoom="1" aria-label="Zoom in">+</button>
        <span class="ocr-zoom-hint">or pinch to zoom</span>
      </div>
      <div class="ocr-search-bar">
        <input id="ocr-search" class="search-input" type="search" placeholder="🔍 Search OCR text..." aria-label="Search OCR text" />
        <button id="clear-search" class="search-clear" type="button" aria-label="Clear OCR search" hidden>×</button>
      </div>
      <div class="ocr-search-tools">
        <span id="ocr-match-count" class="match-count">0 matches</span>
        <div>
          <button id="ocr-prev" type="button" disabled aria-label="Previous search match">← Prev match</button>
          <button id="ocr-next" type="button" disabled aria-label="Next search match">Next match →</button>
        </div>
      </div>
      <div id="ocr-panel">{ocr_fragment}</div>
      <div class="note-box">The plain text OCR version is auto-generated and may contain errors so it is always best to double check with the original PDF. OCR (Optical Character Recognition) is technology that turns images of text into editable, searchable digital text.</div>
    </div>

    <!-- Parish Links Section -->
    <section class="parish-section">
      <h2 class="section-heading">{html.escape(parish_section_heading)}</h2>
      <input id="parish-filter" class="parish-filter" type="search" placeholder="🔍 Filter parishes..." aria-label="Filter parishes" />
      {parish_links_html}
    </section>
  </div>
  <!-- Support Banner -->
  <div style="max-width:1100px;margin:24px auto 0;padding:0 16px;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;background:#fff;border:1px solid #d6ecea;border-radius:12px;padding:14px 18px;">
      <span style="font-size:0.95rem;color:#4b5563;">📊 <span id="view-count">–</span> views this week</span>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <a href="https://github.com/Frankytyrone/parish_harvester" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;background:#24292e;color:#fff;border-radius:8px;font-weight:600;font-size:0.9rem;text-decoration:none;">⭐ Star on GitHub</a>
        <a href="https://buymeacoffee.com/frankytyrone" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;background:#FFDD00;color:#000;border-radius:8px;font-weight:700;font-size:0.9rem;text-decoration:none;">☕ Buy Me a Coffee</a>
      </div>
    </div>
  </div>
  <footer>
    <div class="footer-inner">
      <span>© 2026 Parish Press — Free forever for all Irish parishes</span>
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <a href="https://github.com/Frankytyrone/parish_harvester" target="_blank" rel="noopener noreferrer">GitHub</a>
        <a href="https://buymeacoffee.com/frankytyrone" target="_blank" rel="noopener noreferrer">☕ Donate</a>
      </div>
    </div>
  </footer>

  <script>
    // PDF fullscreen shortcut (the browser's own PDF viewer already
    // supplies page number / zoom / print controls inside the iframe).
    (function () {{
      var wrap = document.getElementById('pdf-frame-wrap');
      var btn = document.getElementById('pdf-fullscreen-btn');
      if (!wrap || !btn) return;
      btn.addEventListener('click', function () {{
        try {{
          if (wrap.requestFullscreen) {{
            wrap.requestFullscreen();
          }} else if (wrap.webkitRequestFullscreen) {{
            wrap.webkitRequestFullscreen();
          }}
        }} catch (e) {{}}
      }});
    }})();

    (function () {{
      var KEY = 'ph_ocr_scale';
      var percents = [75, 85, 100, 115, 130, 150, 175, 200];
      var root = document.getElementById('ocr-panel');
      var label = document.getElementById('ocr-zoom-pct');
      if (!root) return;
      function apply(pct) {{
        root.style.setProperty('--ocr-scale', String(pct / 100));
        if (label) label.textContent = pct + '%';
        try {{ localStorage.setItem(KEY, String(pct)); }} catch (e) {{}}
      }}
      var saved = 100;
      try {{
        var raw = localStorage.getItem(KEY);
        if (raw) {{
          var n = parseFloat(raw);
          if (n > 0 && n < 3) saved = Math.round(n * 100);
          else if (n >= 50 && n <= 250) saved = Math.round(n);
        }}
      }} catch (e) {{}}
      if (percents.indexOf(saved) < 0) {{
        saved = percents.reduce(function (best, p) {{
          return Math.abs(p - saved) < Math.abs(best - saved) ? p : best;
        }}, 100);
      }}
      apply(saved);
      document.querySelectorAll('[data-ocr-zoom]').forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          var dir = parseInt(btn.getAttribute('data-ocr-zoom'), 10) || 0;
          var idx = percents.indexOf(saved);
          if (idx < 0) idx = percents.indexOf(100);
          idx = Math.max(0, Math.min(percents.length - 1, idx + dir));
          saved = percents[idx];
          apply(saved);
        }});
      }});
    }})();

    (function () {{
      const ocrPanel = document.getElementById('ocr-panel');
      const ocrSearch = document.getElementById('ocr-search');
      const clearSearch = document.getElementById('clear-search');
      const matchCount = document.getElementById('ocr-match-count');
      const prevMatchBtn = document.getElementById('ocr-prev');
      const nextMatchBtn = document.getElementById('ocr-next');
      const parishFilter = document.getElementById('parish-filter');
      const parishItems = Array.from(document.querySelectorAll('.parish-item'));
      const parishEmpty = document.getElementById('parish-empty');
      if (!ocrPanel || !ocrSearch) return;
      const originalOcrHtml = ocrPanel.innerHTML;
      let ocrMatches = [];
      let currentMatchIndex = -1;

      function escapeRegExp(text) {{
        const specials = new Set(['\\\\', '^', '$', '.', '|', '?', '*', '+', '(', ')', '[', ']', '{{', '}}']);
        return Array.from(text).map((ch) => specials.has(ch) ? `\\\\${{ch}}` : ch).join('');
      }}

      function scrollToMatch(idx) {{
        if (!ocrMatches.length || idx < 0 || idx >= ocrMatches.length) return;
        ocrMatches.forEach((mark) => mark.classList.remove('search-active'));
        const target = ocrMatches[idx];
        target.classList.add('search-active');
        const details = target.closest('details.parish-block');
        if (details) details.open = true;
        target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}

      function updateMatchUi() {{
        if (!matchCount || !prevMatchBtn || !nextMatchBtn) return;
        const total = ocrMatches.length;
        if (!total) {{
          matchCount.textContent = '0 matches';
          prevMatchBtn.disabled = true;
          nextMatchBtn.disabled = true;
          return;
        }}
        matchCount.textContent = `${{currentMatchIndex + 1}} / ${{total}} matches`;
        prevMatchBtn.disabled = false;
        nextMatchBtn.disabled = false;
      }}

      function applyOcrSearch(query) {{
        ocrPanel.innerHTML = originalOcrHtml;
        ocrMatches = [];
        currentMatchIndex = -1;
        if (!query) {{
          clearSearch.hidden = true;
          updateMatchUi();
          return;
        }}
        clearSearch.hidden = false;
        const regex = new RegExp(escapeRegExp(query), 'gi');
        const walker = document.createTreeWalker(ocrPanel, NodeFilter.SHOW_TEXT, null);
        const nodes = [];
        while (walker.nextNode()) {{
          const node = walker.currentNode;
          if (node.parentElement && node.parentElement.tagName !== 'MARK' && node.nodeValue.trim()) {{
            nodes.push(node);
          }}
        }}
        nodes.forEach((node) => {{
          const text = node.nodeValue;
          regex.lastIndex = 0;
          if (!regex.test(text)) {{
            return;
          }}
          regex.lastIndex = 0;
          const fragment = document.createDocumentFragment();
          let lastIndex = 0;
          let match = null;
          while ((match = regex.exec(text)) !== null) {{
            if (match.index > lastIndex) {{
              fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
            }}
            const mark = document.createElement('mark');
            mark.textContent = match[0];
            fragment.appendChild(mark);
            ocrMatches.push(mark);
            lastIndex = match.index + match[0].length;
          }}
          if (lastIndex < text.length) {{
            fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
          }}
          node.parentNode.replaceChild(fragment, node);
        }});
        ocrPanel.querySelectorAll('details.parish-block').forEach((details) => {{
          details.open = Boolean(details.querySelector('mark'));
        }});
        if (ocrMatches.length) {{
          currentMatchIndex = 0;
          scrollToMatch(currentMatchIndex);
        }}
        updateMatchUi();
      }}

      ocrSearch.addEventListener('input', function (event) {{
        applyOcrSearch(event.target.value.trim());
      }});
      clearSearch.addEventListener('click', function () {{
        ocrSearch.value = '';
        applyOcrSearch('');
        ocrSearch.focus();
      }});
      prevMatchBtn.addEventListener('click', function () {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex - 1 + ocrMatches.length) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});
      nextMatchBtn.addEventListener('click', function () {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex + 1) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});
      ocrSearch.addEventListener('keydown', function (event) {{
        if (event.key === 'Enter' && ocrMatches.length) {{
          event.preventDefault();
          currentMatchIndex = (currentMatchIndex + 1) % ocrMatches.length;
          updateMatchUi();
          scrollToMatch(currentMatchIndex);
        }}
      }});

      if (parishFilter) {{
        parishFilter.addEventListener('input', function (event) {{
          const term = event.target.value.trim().toLowerCase();
          let visibleCount = 0;
          parishItems.forEach((item) => {{
            const name = (item.dataset.name || '').toLowerCase();
            const matches = !term || name.includes(term);
            item.hidden = !matches;
            if (matches) {{
              visibleCount += 1;
            }}
          }});
          if (parishEmpty) {{
            parishEmpty.hidden = visibleCount !== 0;
          }}
        }});
      }}
      if (parishEmpty) {{
        parishEmpty.hidden = parishItems.length === 0 ? false : true;
      }}

      updateMatchUi();
    }})();

    // ── View Counter (localStorage) ──────────────────────────────────
    (function() {{
      var key = 'ph_views_' + location.pathname;
      var weekKey = 'ph_views_week';
      var now = new Date();
      var weekId = now.getFullYear() + '-W' + String(Math.ceil((now - new Date(now.getFullYear(),0,1)) / 86400000 / 7)).padStart(2,'0');
      try {{
        var views = JSON.parse(localStorage.getItem(key) || '{{}}'  );
        if (views.week !== weekId) {{ views = {{ week: weekId, count: 0 }}; }}
        views.count += 1;
        localStorage.setItem(key, JSON.stringify(views));
        // Update total weekly views across all pages
        var total = JSON.parse(localStorage.getItem(weekKey) || '{{}}'  );
        if (total.week !== weekId) {{ total = {{ week: weekId, count: 0 }}; }}
        total.count += 1;
        localStorage.setItem(weekKey, JSON.stringify(total));
        var el = document.getElementById('view-count');
        if (el) el.textContent = total.count;
      }} catch(e) {{}}
    }})();

    // ── Self-Check: Is this week's bulletin available? ───────────────
    (function() {{
      var generated = document.querySelector('.meta');
      if (!generated) return;
      var text = generated.textContent || '';
      var match = text.match(/(\\d{{4}})-(\\d{{2}})-(\\d{{2}})/);
      if (!match) {{
        match = text.match(/(\\d{{2}})[/](\\d{{2}})[/](\\d{{4}})/);
        if (match) match = [null, match[3], match[2], match[1]];
      }}
      if (!match) return;
      var bulletinDate = new Date(match[1] + '-' + match[2] + '-' + match[3]);
      var now = new Date();
      var daysSince = Math.floor((now - bulletinDate) / 86400000);
      if (daysSince > 8) {{
        var banner = document.createElement('div');
        banner.style.cssText = 'max-width:1100px;margin:12px auto;padding:0 16px;';
        banner.innerHTML = '<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:12px 16px;color:#991b1b;font-weight:600;text-align:center;">⚠️ This bulletin is ' + daysSince + ' days old. A newer version may be available — check back after Sunday\\'s harvest run.</div>';
        var page = document.querySelector('.page');
        if (page) page.insertBefore(banner, page.firstChild);
      }}
    }})();
  </script>
</body>
</html>
"""


def regenerate_viewer_from_existing(existing_path: Path) -> Path:
    """Rebuild a viewer page (and OCR-only page) from an older on-disk HTML file."""
    match = VIEWER_FILE_PATTERN.match(existing_path.name)
    if not match:
        raise ValueError(f"Not a viewer file: {existing_path.name}")
    diocese, bulletin_date = match.group(1), match.group(2)
    if diocese not in DIOCESES:
        raise ValueError(f"Unknown diocese key in viewer file: {diocese}")
    config = DIOCESES[diocese]
    raw_html = existing_path.read_text(encoding="utf-8")
    page_match = re.search(r"Page 1 of (\d+)", raw_html)
    page_count = int(page_match.group(1)) if page_match else 1
    if page_count == 1:
        pdf_candidate = DOCS_DIR / "mega_pdf" / config.pdf_filename
        if pdf_candidate.exists():
            try:
                page_count = count_pdf_pages(pdf_candidate)
            except Exception:
                page_count = 1
    panel_match = OCR_PANEL_PATTERN.search(raw_html)
    if not panel_match:
        panel_match = re.search(
            r'<div class="ocr-panel">(.*?)</div>\s*<div class="note-box">',
            raw_html,
            re.DOTALL | re.IGNORECASE,
        )
    if not panel_match:
        raise ValueError(f"Could not find OCR panel in {existing_path}")
    ocr_fragment = panel_match.group(1).strip()
    parish_links = parse_parish_links(config.evidence_path)
    ocr_fragment = prepare_ocr_fragment(diocese, ocr_fragment, parish_links)
    output_path = BULLETINS_DIR / existing_path.name
    output_path.write_text(
        render_viewer_page(config, bulletin_date, page_count, ocr_fragment, parish_links),
        encoding="utf-8",
    )
    ocr_only_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}-ocr.html"
    ocr_only_path.write_text(
        render_ocr_standalone_page(config, bulletin_date, ocr_fragment, viewer_href=output_path.name),
        encoding="utf-8",
    )
    pdf_only_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}-pdf.html"
    pdf_only_path.write_text(
        render_pdf_standalone_page(config, bulletin_date, pdf_href=_pdf_href(config), viewer_href=output_path.name),
        encoding="utf-8",
    )
    return output_path


def write_viewer_page(diocese: str, bulletin_date: str, pdf_path: Path, ocr_html_path: Path) -> Path:
    config = DIOCESES[diocese]
    page_count = count_pdf_pages(pdf_path)
    ocr_fragment = extract_ocr_fragment(ocr_html_path)
    parish_links = parse_parish_links(config.evidence_path)
    ocr_plain_text = _fragment_to_plain_text(ocr_fragment)
    ocr_fragment = prepare_ocr_fragment(diocese, ocr_fragment, parish_links)
    output_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}.html"
    output_path.write_text(
        render_viewer_page(config, bulletin_date, page_count, ocr_fragment, parish_links),
        encoding="utf-8",
    )
    ocr_only_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}-ocr.html"
    ocr_only_path.write_text(
        render_ocr_standalone_page(config, bulletin_date, ocr_fragment, viewer_href=output_path.name),
        encoding="utf-8",
    )
    pdf_only_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}-pdf.html"
    pdf_only_path.write_text(
        render_pdf_standalone_page(config, bulletin_date, pdf_href=_pdf_href(config), viewer_href=output_path.name),
        encoding="utf-8",
    )
    _write_parish_reader_outputs(diocese, bulletin_date, ocr_plain_text, parish_links)
    return output_path


def scan_viewer_entries() -> list[ViewerEntry]:
    entries: list[ViewerEntry] = []
    if not BULLETINS_DIR.exists():
        return entries
    for path in BULLETINS_DIR.glob("*.html"):
        if path.name == "index.html":
            continue
        match = VIEWER_FILE_PATTERN.match(path.name)
        if not match:
            continue
        diocese = match.group(1)
        if diocese not in DIOCESES:
            continue
        entries.append(ViewerEntry(diocese=diocese, date=match.group(2), path=path))
    return sorted(entries, key=lambda entry: (entry.date, entry.diocese), reverse=True)


def write_bulletins_index(entries: list[ViewerEntry]) -> None:
    items = []
    for entry in entries:
        config = DIOCESES[entry.diocese]
        items.append(
            f"<li><a href=\"{entry.path.name}\">{html.escape(config.display_name)} — {html.escape(format_uk_date(entry.date))}</a></li>"
        )
    if not items:
        items.append("<li>No OCR bulletin viewer pages have been generated yet.</li>")
    BULLETINS_DIR.mkdir(parents=True, exist_ok=True)
    (BULLETINS_DIR / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OCR Bulletin Archive</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f7faf9; color: {TEXT}; }}
    .page {{ max-width: 960px; margin: 0 auto; padding: 28px 20px 40px; }}
    h1 {{ margin: 0 0 10px; color: {TEAL}; }}
    p {{ color: #4b5563; }}
    .archive {{ margin-top: 24px; background: #fff; border: 1px solid #d6ecea; border-radius: 16px; padding: 20px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.06); }}
    ul {{ margin: 0; padding-left: 24px; }}
    li {{ margin: 10px 0; }}
    a {{ color: {TEAL}; font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="page">
    <a href="../index.html">← Back to dashboard</a>
    <h1>OCR Bulletin Archive</h1>
    <p>Newest generated bulletin viewer pages appear first.</p>
    <div class="archive">
      <ul>{''.join(items)}</ul>
    </div>
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )


def write_root_index(entries: list[ViewerEntry]) -> None:
    latest_by_diocese: dict[str, ViewerEntry] = {}
    cards = []
    for entry in entries:
        if entry.diocese not in latest_by_diocese:
            latest_by_diocese[entry.diocese] = entry
    for diocese in DIOCESES.values():
        latest = latest_by_diocese.get(diocese.key)
        ocr_href = f"bulletins/{latest.path.name}" if latest else "bulletins/index.html"
        ocr_label = format_uk_date(latest.date) if latest else "Archive"
        cards.append(
            f"""
        <article class="card">
          <p class="eyebrow">Mega PDF card</p>
          <h2>{html.escape(diocese.display_name)}</h2>
          <p>Latest OCR viewer: <strong>{html.escape(ocr_label)}</strong></p>
          <div class="actions">
            <a class="button secondary" href="mega_pdf/index.html#{diocese.key}">👁 View Online</a>
            <a class="button primary" href="{ocr_href}">📖 Read OCR Text</a>
            <a class="button secondary" href="mega_pdf/{diocese.pdf_filename}" download>⬇ Download PDF</a>
          </div>
        </article>
            """
        )
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Parish Bulletin Dashboard</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #eff9f8 0%, #f8fbfb 100%); color: {TEXT}; }}
    .hero {{ padding: 44px 20px 24px; background: linear-gradient(135deg, {TEAL} 0%, #114b4b 100%); color: white; }}
    .hero-inner, .content {{ max-width: 1160px; margin: 0 auto; }}
    .hero h1 {{ margin: 0 0 10px; font-size: clamp(2.1rem, 4vw, 3.2rem); }}
    .hero p {{ margin: 0; max-width: 760px; color: rgba(255,255,255,0.88); font-size: 1.05rem; }}
    .content {{ padding: 28px 20px 40px; }}
    .section-title {{ margin: 0 0 16px; color: {TEAL}; font-size: 1.45rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
    .card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 22px; box-shadow: 0 14px 34px rgba(26, 122, 122, 0.08); }}
    .eyebrow {{ margin: 0 0 8px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; font-weight: 700; }}
    .card h2 {{ margin: 0 0 10px; font-size: 1.45rem; }}
    .card p {{ margin: 0 0 18px; color: #4b5563; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; padding: 11px 16px; border-radius: 999px; font-weight: 700; text-decoration: none; }}
    .button.primary {{ background: {TEAL}; color: white; }}
    .button.secondary {{ background: #edf7f6; color: {TEAL}; border: 1px solid #cfe8e6; }}
    .archive-card {{ margin-top: 24px; background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 20px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.06); }}
    .archive-card a {{ color: {TEAL}; font-weight: 700; text-decoration: none; }}
    .archive-card a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="hero-inner">
      <h1>Parish Bulletin Dashboard</h1>
      <p>Read the latest diocesan mega PDFs, switch to OCR side-by-side viewer pages, and browse the growing bulletin archive published to GitHub Pages.</p>
    </div>
  </section>
  <main class="content">
    <h2 class="section-title">Mega PDF cards</h2>
    <div class="cards">{''.join(cards)}</div>
    <div class="archive-card">
      <p><a href="bulletins/index.html">Browse the full OCR bulletin archive</a></p>
      <p><a href="mega_pdf/index.html">Open the mega PDF tab viewer</a></p>
      <p><a href="search/">Search all bulletins</a></p>
    </div>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def rebuild_indexes() -> None:
    entries = scan_viewer_entries()
    write_bulletins_index(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate side-by-side OCR bulletin viewer pages.")
    parser.add_argument("--diocese", choices=sorted(DIOCESES))
    parser.add_argument("--date")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--ocr-html", type=Path)
    parser.add_argument("--rebuild-indexes", action="store_true")
    parser.add_argument("--regenerate-from", type=Path, help="Rebuild viewer HTML from an existing on-disk viewer file")
    args = parser.parse_args()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    BULLETINS_DIR.mkdir(parents=True, exist_ok=True)

    if args.rebuild_indexes:
        rebuild_indexes()
        return

    if args.regenerate_from:
        regenerate_viewer_from_existing(args.regenerate_from.resolve())
        rebuild_indexes()
        return

    if not all([args.diocese, args.date, args.pdf, args.ocr_html]):
        parser.error("--diocese, --date, --pdf, and --ocr-html are required unless --rebuild-indexes is used.")

    write_viewer_page(args.diocese, args.date, args.pdf, args.ocr_html)
    rebuild_indexes()


if __name__ == "__main__":
    main()
