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
}

HEADER_PATTERN = re.compile(r"^#\s*---\s*(.*?)\s*---\s*$")
OCR_BODY_PATTERN = re.compile(r'<div class="scrollable-viewer">\s*(.*?)\s*</div>\s*</body>', re.DOTALL | re.IGNORECASE)
OCR_PAGE_HEADING_PATTERN = re.compile(r"<h2>\s*Page\s+(\d+)\s*</h2>", re.IGNORECASE)
VIEWER_FILE_PATTERN = re.compile(r"^(derry|down_and_connor)-(\d{4}-\d{2}-\d{2})\.html$")
OCR_PANEL_PATTERN = re.compile(
    r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
    re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
TEAL = "#1a6b6b"
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


DIOCESES = {
    "derry": DioceseConfig(
        key="derry",
        display_name="Derry Diocese",
        headline="DERRY DIOCESE BIG BULLETIN",
        evidence_path=REPO_ROOT / "parishes" / "derry_diocese_bulletin_urls.txt",
        pdf_filename="derry_mega_bulletin.pdf",
    ),
    "down_and_connor": DioceseConfig(
        key="down_and_connor",
        display_name="Down & Connor Diocese",
        headline="DOWN & CONNOR DIOCESE BIG BULLETIN",
        evidence_path=REPO_ROOT / "parishes" / "down_and_connor_bulletin_urls.txt",
        pdf_filename="down_and_connor_mega_bulletin.pdf",
    ),
}


def parse_parish_links(path: Path) -> list[tuple[str, str]]:
    parish_links: list[tuple[str, str]] = []
    current_name: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        header = HEADER_PATTERN.match(line)
        if header:
            current_name = header.group(1).strip()
            continue
        if not line or line.startswith("#"):
            continue
        if current_name:
            parish_links.append((current_name, line))
            current_name = None
    return parish_links


def extract_ocr_fragment(path: Path) -> str:
    raw_html = path.read_text(encoding="utf-8")
    match = OCR_BODY_PATTERN.search(raw_html)
    if not match:
        raise ValueError(f"Could not find OCR content wrapper in {path}")
    fragment = OCR_PAGE_HEADING_PATTERN.sub(r"<h3>PAGE \1</h3>", match.group(1).strip())
    return fragment


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

def _render_parish_links(parish_links: list[tuple[str, str]]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish bulletin links were found for this diocese yet.</p>'
    sorted_links = sorted(parish_links, key=lambda pair: pair[0].lower())
    items = []
    for name, url in sorted_links:
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
        '<ul id="parish-grid" class="parish-grid">{items}</ul>'
    ).format(items="".join(items))


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
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} Bulletin Text — {html.escape(uk_bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f7f8fb;
      color: {TEXT};
      line-height: 1.75;
      font-size: 17px;
      -webkit-text-size-adjust: 100%;
    }}
    a {{ color: {TEAL}; text-decoration: none; font-weight: 600; }}
    a:hover {{ text-decoration: underline; }}
    .page {{ max-width: 900px; margin: 0 auto; padding: 20px 16px 40px; }}
    .back-link {{ display: inline-block; margin-bottom: 14px; font-weight: 700; color: {TEAL}; }}
    h1 {{ margin: 0 0 8px; color: {TEAL}; font-size: clamp(1.4rem, 4vw, 2rem); }}
    .meta {{ color: #6b7280; font-size: 0.95rem; margin-bottom: 18px; }}
    .ocr-body {{
      background: #fff;
      border: 1px solid #d6ecea;
      border-radius: 14px;
      padding: 20px 18px;
      box-shadow: 0 4px 12px rgba(26, 107, 107, 0.06);
    }}
    .ocr-body h1, .ocr-body h2, .ocr-body h3 {{ color: {TEAL}; margin: 16px 0 10px; }}
    .ocr-body h3.ocr-page-heading {{
      font-size: 0.95rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-top: 24px;
    }}
    .ocr-body p {{ margin: 0 0 12px; white-space: pre-wrap; }}
    .ocr-body hr {{ border: 0; border-top: 1px solid #d4dfde; margin: 20px 0; }}
    .ocr-body mark {{ background: #fff3cd; padding: 0 2px; border-radius: 2px; }}
    .ocr-body mark.search-active {{ background: #fde047; outline: 2px solid #0f5e5e; }}
    .ocr-search-bar {{ position: relative; margin-bottom: 10px; }}
    .search-input {{ width: 100%; min-height: 48px; border: 1px solid #bdd7d5; border-radius: 8px; padding: 10px 40px 10px 12px; font-size: 1rem; }}
    .search-clear {{ position: absolute; right: 8px; top: 50%; transform: translateY(-50%); width: 32px; height: 32px; border: 0; background: transparent; color: #6b7280; font-size: 1.2rem; cursor: pointer; }}
    .search-clear[hidden] {{ display: none; }}
    .ocr-search-tools {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
    .ocr-search-tools button {{ border: 0; border-radius: 6px; background: {TEAL}; color: #fff; font-weight: 700; min-height: 40px; padding: 8px 14px; cursor: pointer; }}
    .ocr-search-tools button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    .match-count {{ color: #6b7280; font-size: 0.92rem; font-weight: 700; }}
    .ocr-scroll {{ max-height: 70vh; overflow-y: auto; -webkit-overflow-scrolling: touch; }}
    .note-box {{
      margin-top: 16px;
      padding: 12px 16px;
      border-radius: 10px;
      background: #fff4df;
      border: 1px solid #f5d08d;
      color: #713f12;
      font-weight: 600;
      font-size: 0.95rem;
    }}
    @media (max-width: 600px) {{
      .page {{ padding: 16px 12px 32px; }}
      .ocr-body {{ padding: 16px 14px; font-size: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{html.escape(viewer_href, quote=True)}">← Back to bulletin viewer</a>
    <p class="meta">{html.escape(diocese_label)} · {html.escape(uk_bulletin_date)}</p>
    <h1>Parish Bulletin Text</h1>
    <div class="ocr-search-bar">
      <input id="ocr-search" class="search-input" type="search" placeholder="🔍 Search (e.g. mass, bingo, parish name)..." aria-label="Search bulletin text" />
      <button id="clear-search" class="search-clear" type="button" aria-label="Clear search" hidden>×</button>
    </div>
    <div class="ocr-search-tools">
      <span id="ocr-match-count" class="match-count">0 matches</span>
      <div>
        <button id="ocr-prev" type="button" disabled>← Prev match</button>
        <button id="ocr-next" type="button" disabled>Next match →</button>
      </div>
    </div>
    <div class="ocr-scroll">
      <div class="ocr-body" id="ocr-text">{ocr_fragment}</div>
    </div>
    <div class="note-box">This text is auto-generated from the parish bulletin PDF. Irish (Gaeilge) and English are preserved as printed. Please verify mass times and names against the original PDF.</div>
  </div>
  <script>
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


def render_viewer_page(config: DioceseConfig, bulletin_date: str, page_count: int, ocr_fragment: str, parish_links: list[tuple[str, str]]) -> str:
    pdf_href = f"../mega_pdf/{config.pdf_filename}"
    ocr_standalone_href = f"{config.key}-{bulletin_date}-ocr.html"
    archive_href = "index.html"
    diocese_label = _diocese_label(config.display_name)
    uk_bulletin_date = format_uk_date(bulletin_date)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} Bulletin Viewer — {html.escape(uk_bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f7f8fb;
      color: {TEXT};
      line-height: 1.6;
    }}
    a {{ color: {TEAL}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{ max-width: 1400px; margin: 0 auto; padding: 20px 16px 40px; }}
    .back-link {{ display: inline-block; margin-bottom: 14px; font-weight: 700; color: {TEAL}; }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .diocese-label {{ margin: 0 0 6px; color: {ACCENT}; font-size: 0.95rem; letter-spacing: 0.15em; text-transform: uppercase; font-weight: 800; }}
    h1 {{ margin: 0 0 8px; color: {TEAL}; font-size: clamp(1.8rem, 3vw, 2.5rem); }}
    .meta {{ color: #6b7280; font-size: 0.95rem; }}
    
    /* Tabs */
    .tabs {{
      display: flex;
      justify-content: center;
      gap: 10px;
      margin: 0 0 20px;
      padding: 16px 0;
      background: #e8edf5;
      border-bottom: 2px solid #c7d2e8;
    }}
    .tab-btn {{
      padding: 12px 28px;
      border: 2px solid {TEAL};
      border-radius: 8px;
      background: white;
      color: {TEAL};
      font-weight: 700;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .tab-btn:hover {{
      background: #f0f4f8;
    }}
    .tab-btn.active {{
      background: {TEAL};
      color: white;
    }}
    
    /* Panel container */
    .panel-container {{ position: relative; }}
    .view-panel {{
      display: none;
      background: white;
      border: 1px solid #d6ecea;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 4px 12px rgba(26, 107, 107, 0.08);
    }}
    .view-panel.active {{ display: block; }}
    
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
    
    /* PDF View */
    .pdf-controls {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin: 12px 0;
      font-weight: 700;
      flex-wrap: wrap;
    }}
    .pdf-controls button {{
      border: 0;
      border-radius: 6px;
      background: {TEAL};
      color: white;
      font-weight: 700;
      padding: 10px 20px;
      cursor: pointer;
      font-size: 0.95rem;
    }}
    .pdf-controls button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    .pdf-canvas-wrap {{
      height: 75vh;
      min-height: 500px;
      overflow: auto;
      border: 1px solid #c7dcda;
      border-radius: 10px;
      background: #f2f5f5;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 10px;
    }}
    #pdf-canvas {{ display: block; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15); max-width: 100%; }}
    
    /* OCR View */
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
    #ocr-panel {{
      height: 70vh;
      min-height: 500px;
      overflow-y: auto;
      border: 1px solid #d9e4e3;
      border-radius: 10px;
      padding: 24px;
      background: white;
      font-size: 17px;
      line-height: 1.8;
      color: {TEXT};
    }}
    #ocr-panel h1, #ocr-panel h2, #ocr-panel h3 {{
      color: {TEAL};
      margin-top: 16px;
      margin-bottom: 10px;
    }}
    #ocr-panel h3.ocr-page-heading {{
      font-size: 1rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-top: 24px;
    }}
    #ocr-panel hr {{ border: 0; border-top: 1px solid #d4dfde; margin: 20px 0; }}
    #ocr-panel p {{ margin: 0 0 12px; white-space: pre-wrap; }}
    #ocr-panel mark {{ background: #fef08a; padding: 1px 3px; border-radius: 2px; }}
    #ocr-panel mark.search-active {{ background: #fde047; outline: 2px solid #0f5e5e; }}
    #ocr-panel a {{ color: {TEAL}; font-weight: 600; }}
    .note-box {{
      margin-top: 16px;
      padding: 12px 16px;
      border-radius: 10px;
      background: #fff4df;
      border: 1px solid #f5d08d;
      color: #713f12;
      font-weight: 600;
      font-size: 0.95rem;
    }}
    
    /* Parish Section */
    .parish-section {{
      margin-top: 32px;
      background: white;
      border: 1px solid #d6ecea;
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 4px 12px rgba(26, 107, 107, 0.06);
    }}
    .parish-section h2 {{
      margin: 0 0 18px;
      color: {TEAL};
      font-size: 1.4rem;
      font-weight: 800;
      text-align: center;
    }}
    .parish-filter {{
      width: 100%;
      border: 1px solid #bdd7d5;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 1rem;
      margin-bottom: 16px;
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
      max-width: 1400px;
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
      .tabs {{ flex-direction: column; align-items: stretch; padding: 12px; }}
      .tab-btn {{ width: 100%; }}
    }}
    @media (max-width: 600px) {{
      .page {{ padding: 16px 12px; }}
      ul.parish-grid {{ grid-template-columns: 1fr; }}
      .pdf-controls, .ocr-search-tools {{ flex-direction: column; }}
      .pdf-canvas-wrap, #ocr-panel {{
        height: auto;
        min-height: 55vh;
        max-height: 70vh;
      }}
      .pdf-controls button, .ocr-search-tools button, .tab-btn {{
        min-height: 48px;
        width: 100%;
      }}
      .panel-toolbar {{ justify-content: stretch; }}
      .toolbar-btn {{ flex: 1; justify-content: center; min-height: 48px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{archive_href}">← Back to bulletin archive</a>
    <header class="header">
      <p class="diocese-label">{html.escape(diocese_label)}</p>
      <h1>{html.escape(config.headline)}</h1>
      <p class="meta">Generated for {html.escape(uk_bulletin_date)}.</p>
    </header>

    <!-- Tabs -->
    <div class="tabs" role="tablist" aria-label="Bulletin view">
      <button class="tab-btn active" type="button" role="tab" aria-selected="true" data-tab="pdf" onclick="switchTab('pdf', this)">📄 Parish Bulletin (PDF)</button>
      <button class="tab-btn" type="button" role="tab" aria-selected="false" data-tab="ocr" onclick="switchTab('ocr', this)">📝 Searchable Bulletin Text</button>
    </div>

    <!-- Panel Container -->
    <div class="panel-container">
      
      <!-- PDF Panel -->
      <div id="panel-pdf" class="view-panel active">
        <div class="panel-toolbar">
          <a class="toolbar-btn" href="{pdf_href}" target="_blank" rel="noopener noreferrer">↗ Open PDF in new tab</a>
          <a class="toolbar-btn" href="{pdf_href}" download>⬇ Download PDF</a>
        </div>
        <div class="pdf-controls" data-controls="top">
          <button data-action="prev" type="button" aria-label="Previous PDF page">← Previous page</button>
          <span data-role="page-indicator">Page 1 of {page_count}</span>
          <button data-action="next" type="button" aria-label="Next PDF page">Next page →</button>
        </div>
        <div id="pdf-canvas-wrap" class="pdf-canvas-wrap">
          <canvas id="pdf-canvas" title="{html.escape(config.display_name)} bulletin PDF"></canvas>
        </div>
        <div class="pdf-controls" data-controls="bottom">
          <button data-action="prev" type="button" aria-label="Previous PDF page">← Previous page</button>
          <span data-role="page-indicator">Page 1 of {page_count}</span>
          <button data-action="next" type="button" aria-label="Next PDF page">Next page →</button>
        </div>
      </div>

      <!-- OCR Panel -->
      <div id="panel-ocr" class="view-panel">
        <div class="panel-toolbar">
          <a class="toolbar-btn" href="{ocr_standalone_href}" target="_blank" rel="noopener noreferrer">↗ Open bulletin text in new tab</a>
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
        <div class="note-box">This bulletin text is auto-generated from the PDF. Irish (Gaeilge) and English are kept as printed. Please verify mass times and names against the original PDF.</div>
      </div>

    </div>

    <!-- Parish Links Section -->
    <section class="parish-section">
      <h2>{html.escape(diocese_label)} Parishes with Working Bulletin Links</h2>
      <input id="parish-filter" class="parish-filter" type="search" placeholder="🔍 Filter parishes..." aria-label="Filter parishes" />
      {_render_parish_links(parish_links)}
    </section>
  </div>
  <!-- Support Banner -->
  <div style="max-width:1400px;margin:24px auto 0;padding:0 16px;">
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

  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <script>
    // Tab Switching
    function switchTab(tabName, button) {{
      document.querySelectorAll('.view-panel').forEach(function(panel) {{
        panel.classList.remove('active');
      }});
      document.querySelectorAll('.tab-btn').forEach(function(btn) {{
        btn.classList.remove('active');
        btn.setAttribute('aria-selected', 'false');
      }});
      document.getElementById('panel-' + tabName).classList.add('active');
      button.classList.add('active');
      button.setAttribute('aria-selected', 'true');
    }}

    (function () {{
      const pdfHref = {pdf_href!r};
      const initialPages = {page_count};
      const canvas = document.getElementById('pdf-canvas');
      const canvasWrap = document.getElementById('pdf-canvas-wrap');
      const context = canvas.getContext('2d');
      const ocrPanel = document.getElementById('ocr-panel');
      const indicators = Array.from(document.querySelectorAll('[data-role="page-indicator"]'));
      const prevButtons = Array.from(document.querySelectorAll('button[data-action="prev"]'));
      const nextButtons = Array.from(document.querySelectorAll('button[data-action="next"]'));
      const ocrSearch = document.getElementById('ocr-search');
      const clearSearch = document.getElementById('clear-search');
      const matchCount = document.getElementById('ocr-match-count');
      const prevMatchBtn = document.getElementById('ocr-prev');
      const nextMatchBtn = document.getElementById('ocr-next');
      const parishFilter = document.getElementById('parish-filter');
      const parishItems = Array.from(document.querySelectorAll('.parish-item'));
      const parishEmpty = document.getElementById('parish-empty');
      const originalOcrHtml = ocrPanel.innerHTML;
      const pdfjs = window['pdfjs-dist/build/pdf'] || window.pdfjsLib;
      let currentPage = 1;
      let totalPages = initialPages;
      let pdfDoc = null;
      let isRendering = false;
      let pendingPage = null;
      let ocrMatches = [];
      let currentMatchIndex = -1;

      if (!pdfjs) {{
        return;
      }}

      pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

      function escapeRegExp(text) {{
        const specials = new Set(['\\\\', '^', '$', '.', '|', '?', '*', '+', '(', ')', '[', ']', '{{', '}}']);
        return Array.from(text).map((ch) => specials.has(ch) ? `\\\\${{ch}}` : ch).join('');
      }}

      function updateControls() {{
        indicators.forEach((indicator) => {{
          indicator.textContent = `Page ${{currentPage}} of ${{totalPages}}`;
        }});
        prevButtons.forEach((button) => {{
          button.disabled = currentPage <= 1 || !pdfDoc;
        }});
        nextButtons.forEach((button) => {{
          button.disabled = currentPage >= totalPages || !pdfDoc;
        }});
      }}

      function queueRender(pageNumber) {{
        if (isRendering) {{
          pendingPage = pageNumber;
          return;
        }}
        renderPage(pageNumber);
      }}

      async function renderPage(pageNumber) {{
        if (!pdfDoc) {{
          return;
        }}
        isRendering = true;
        currentPage = pageNumber;
        updateControls();
        const page = await pdfDoc.getPage(pageNumber);
        const viewport = page.getViewport({{ scale: 1 }});
        const availableWidth = Math.max(canvasWrap.clientWidth - 16, 100);
        const scale = availableWidth / viewport.width;
        const scaledViewport = page.getViewport({{ scale }});
        canvas.width = Math.floor(scaledViewport.width);
        canvas.height = Math.floor(scaledViewport.height);
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        await page.render({{
          canvasContext: context,
          viewport: scaledViewport,
        }}).promise;
        // PDF page changes do not scroll the bulletin text panel.
        isRendering = false;
        if (pendingPage !== null) {{
          const queued = pendingPage;
          pendingPage = null;
          queueRender(queued);
        }}
      }}

      function goToPage(nextPage) {{
        if (!pdfDoc) {{
          return;
        }}
        const clamped = Math.min(Math.max(nextPage, 1), totalPages);
        if (clamped === currentPage && !isRendering) {{
          return;
        }}
        queueRender(clamped);
      }}

      prevButtons.forEach((button) => {{
        button.addEventListener('click', function (event) {{
          event.preventDefault();
          event.stopPropagation();
          goToPage(currentPage - 1);
        }});
      }});
      nextButtons.forEach((button) => {{
        button.addEventListener('click', function (event) {{
          event.preventDefault();
          event.stopPropagation();
          goToPage(currentPage + 1);
        }});
      }});

      new ResizeObserver(function () {{
        if (pdfDoc) {{
          queueRender(currentPage);
        }}
      }}).observe(canvasWrap);

      pdfjs.getDocument(pdfHref).promise.then(function (doc) {{
        pdfDoc = doc;
        totalPages = doc.numPages || initialPages;
        updateControls();
        queueRender(currentPage);
      }}).catch(function () {{
        updateControls();
      }});

      function scrollToMatch(idx) {{
        if (!ocrMatches.length || idx < 0 || idx >= ocrMatches.length) return;
        ocrMatches.forEach((mark) => mark.classList.remove('search-active'));
        const target = ocrMatches[idx];
        target.classList.add('search-active');
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

      parishFilter.addEventListener('input', function (event) {{
        const term = event.target.value.trim().toLowerCase();
        let visibleCount = 0;
        parishItems.forEach((item) => {{
          const matches = item.dataset.name.includes(term);
          item.hidden = !matches;
          if (matches) {{
            visibleCount += 1;
          }}
        }});
        if (parishEmpty) {{
          parishEmpty.hidden = visibleCount !== 0;
        }}
      }});

      updateControls();
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
      var match = text.match(/(\d{{4}})-(\d{{2}})-(\d{{2}})/);
      if (!match) {{
        match = text.match(/(\d{{2}})\/(\d{{2}})\/(\d{{4}})/);
        if (match) match = [null, match[3], match[2], match[1]];
      }}
      if (!match) return;
      var bulletinDate = new Date(match[1] + '-' + match[2] + '-' + match[3]);
      var now = new Date();
      var daysSince = Math.floor((now - bulletinDate) / 86400000);
      if (daysSince > 8) {{
        var banner = document.createElement('div');
        banner.style.cssText = 'max-width:1400px;margin:12px auto;padding:0 16px;';
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
    config = DIOCESES[diocese]
    raw_html = existing_path.read_text(encoding="utf-8")
    page_match = re.search(r"Page 1 of (\d+)", raw_html)
    page_count = int(page_match.group(1)) if page_match else 1
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
    return output_path


def write_viewer_page(diocese: str, bulletin_date: str, pdf_path: Path, ocr_html_path: Path) -> Path:
    config = DIOCESES[diocese]
    page_count = count_pdf_pages(pdf_path)
    ocr_fragment = extract_ocr_fragment(ocr_html_path)
    ocr_plain_text = _fragment_to_plain_text(ocr_fragment)
    parish_links = parse_parish_links(config.evidence_path)
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
        entries.append(ViewerEntry(diocese=match.group(1), date=match.group(2), path=path))
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
