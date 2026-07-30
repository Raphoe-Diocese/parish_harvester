from __future__ import annotations

import json
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from harvester.fetcher import parse_evidence_file
from harvester.page_renderer import (
    render_diocese_raphoe_page,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
RECIPES_DIR = REPO_ROOT / "parishes" / "recipes"
BULLETINS_DIR = DOCS_DIR / "bulletins"

LIVE_DIOCESES = {"raphoe", "derry", "down-and-connor"}
RELIABILITY_PATH = DOCS_DIR / "reliability.json"
REPORT_PATH = REPO_ROOT / "Bulletins" / "report.json"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Raphoe-Diocese/parish_harvester/main/Bulletins/current"
EVIDENCE_DIOCESE_KEYS = {
    "derry": "derry_diocese",
    "down-and-connor": "down_and_connor",
    "raphoe": "raphoe_diocese",
}

_CANONICAL_DIOCESES = [
    "Armagh",
    "Dublin",
    "Cashel and Emly",
    "Tuam",
    "Clogher",
    "Cloyne",
    "Cork and Ross",
    "Derry",
    "Down and Connor",
    "Dromore",
    "Elphin",
    "Ferns",
    "Galway Kilmacduagh and Kilfenora",
    "Kerry",
    "Kildare and Leighlin",
    "Killala",
    "Killaloe",
    "Limerick",
    "Meath",
    "Ossory",
    "Raphoe",
    "Waterford and Lismore",
    "Achonry",
    "Ardagh and Clonmacnoise",
    "Kilmore",
    "Kilfenora-and-Kilmacduagh",
]


@dataclass(frozen=True)
class DioceseCard:
    key: str
    name: str


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(ch for ch in normalized if ord(ch) < 128)
    lowered = ascii_value.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return collapsed


def _all_dioceses() -> list[DioceseCard]:
    return [DioceseCard(key=_slugify(name), name=name) for name in _CANONICAL_DIOCESES]


def _recipe_dirs(diocese_key: str) -> list[Path]:
    candidates = {
        RECIPES_DIR / diocese_key,
        RECIPES_DIR / diocese_key.replace("-", "_"),
    }
    return [path for path in candidates if path.is_dir()]


def _recipe_files(diocese_key: str) -> list[Path]:
    files: list[Path] = []
    for recipe_dir in _recipe_dirs(diocese_key):
        files.extend(sorted(recipe_dir.glob("*.json")))
    return files


def _parish_links(diocese_key: str) -> list[dict[str, str]]:
    evidence_key = EVIDENCE_DIOCESE_KEYS.get(diocese_key)
    if evidence_key:
        try:
            entries = parse_evidence_file(evidence_key, REPO_ROOT / "parishes")
        except Exception:
            entries = []
        if entries:
            return [
                {
                    "name": entry.display_name,
                    "url": entry.bulletin_page or entry.example_url,
                }
                for entry in entries
                if (entry.bulletin_page or entry.example_url)
            ]

    links: list[dict[str, str]] = []
    for path in _recipe_files(diocese_key):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        name = (
            str(payload.get("parish_name") or "").strip()
            or str(payload.get("display_name") or "").strip()
            or path.stem.replace("-", " ").replace("_", " ").title()
        )
        url = str(payload.get("start_url") or "").strip()
        if not url:
            continue
        links.append({"name": name, "url": url})
    return links


def _recipe_keys(diocese_key: str) -> set[str]:
    keys: set[str] = set()
    for path in _recipe_files(diocese_key):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            key = str(payload.get("parish_key") or "").strip()
            if key:
                keys.add(key)
                continue
        keys.add(path.stem)
    return keys


def _load_report_sections(report_path: Path) -> tuple[dict, dict, dict, str]:
    """Return (downloaded, failed, skipped, target_date) keyed by parish_key."""
    downloaded: dict[str, dict] = {}
    failed: dict[str, dict] = {}
    skipped: dict[str, dict] = {}
    target_date = ""
    if not report_path.exists():
        return downloaded, failed, skipped, target_date
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return downloaded, failed, skipped, target_date
    target_date = str(payload.get("target_date") or "").strip()
    for section, bucket in (
        ("downloaded", downloaded),
        ("failed", failed),
        ("skipped", skipped),
    ):
        rows = payload.get(section)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("parish") or "").strip()
            if key:
                bucket[key] = row
    return downloaded, failed, skipped, target_date


def _parish_links_with_harvest(diocese_key: str, report_path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Merge evidence/recipe links with this week's harvest report."""
    base_links = _parish_links(diocese_key)
    downloaded, _failed, skipped, _target_date = _load_report_sections(report_path)
    recipe_keys = _recipe_keys(diocese_key)
    stats = {"ok": 0, "skip": 0, "fail": 0}
    merged: list[dict[str, str]] = []
    seen: set[str] = set()

    def _append(name: str, key: str, fallback_url: str) -> None:
        if key in seen:
            return
        seen.add(key)
        if key in downloaded:
            row = downloaded[key]
            url = f"{GITHUB_RAW_BASE}/{key}.pdf"
            local = REPO_ROOT / "Bulletins" / "current" / f"{key}.pdf"
            if not local.exists():
                url = str(row.get("url") or fallback_url or "#")
            merged.append({"name": name, "url": url, "status": "ok"})
            stats["ok"] += 1
        elif key in skipped:
            merged.append({"name": name, "url": fallback_url or "#", "status": "skip"})
            stats["skip"] += 1
        else:
            merged.append({"name": name, "url": fallback_url or "#", "status": "miss"})
            stats["fail"] += 1

    for link in base_links:
        name = str(link.get("name") or "").strip()
        url = str(link.get("url") or "").strip()
        key = _slugify(name).replace("-", "")
        for recipe_key in recipe_keys:
            if recipe_key.replace("_", "") in _slugify(name).replace("-", ""):
                key = recipe_key
                break
        _append(name or key, key, url)

    for recipe_key in sorted(recipe_keys):
        if recipe_key in seen:
            continue
        path = next(
            (p for p in _recipe_files(diocese_key) if p.stem == recipe_key),
            None,
        )
        fallback = ""
        display = recipe_key.replace("-", " ").replace("_", " ").title()
        if path:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                display = str(payload.get("display_name") or display).strip()
                fallback = str(payload.get("start_url") or "").strip()
            except Exception:
                pass
        _append(display, recipe_key, fallback)

    return merged, stats


def _load_downloaded(report_path: Path) -> set[str]:
    if not report_path.exists():
        return set()
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    downloaded = payload.get("downloaded")
    if not isinstance(downloaded, list):
        return set()
    keys: set[str] = set()
    for row in downloaded:
        if not isinstance(row, dict):
            continue
        parish = str(row.get("parish") or "").strip()
        if parish:
            keys.add(parish)
    return keys


def _viewer_pattern(diocese_key: str) -> re.Pattern[str]:
    stem = diocese_key.replace("-", "[-_]")
    return re.compile(rf"^{stem}-(\d{{4}}-\d{{2}}-\d{{2}})\.html$")


def _latest_viewer(diocese_key: str) -> tuple[Path | None, str | None]:
    if not BULLETINS_DIR.exists():
        return None, None
    regex = _viewer_pattern(diocese_key)
    latest: tuple[Path, str] | None = None
    for path in sorted(BULLETINS_DIR.glob("*.html")):
        if path.name == "index.html":
            continue
        match = regex.match(path.name)
        if not match:
            continue
        date_text = match.group(1)
        if latest is None or date_text > latest[1]:
            latest = (path, date_text)
    return latest if latest else (None, None)


def _ocr_html_from_viewer(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    raw_html = path.read_text(encoding="utf-8")
    match = re.search(
        r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _latest_ocr_standalone(diocese_key: str) -> Path | None:
    if not BULLETINS_DIR.exists():
        return None
    stem = diocese_key.replace("-", "[-_]")
    regex = re.compile(rf"^{stem}-(\d{{4}}-\d{{2}}-\d{{2}})-ocr\.html$")
    latest: tuple[Path, str] | None = None
    for path in sorted(BULLETINS_DIR.glob("*.html")):
        match = regex.match(path.name)
        if not match:
            continue
        date_text = match.group(1)
        if latest is None or date_text > latest[1]:
            latest = (path, date_text)
    return latest[0] if latest else None


def _ocr_html_from_standalone(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    raw_html = path.read_text(encoding="utf-8")
    match = re.search(
        r'<div class="ocr-body[^"]*">\s*(.*?)\s*</div>\s*</main>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r'<div class="scrollable-viewer">\s*(.*?)\s*</div>\s*</body>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


def _ocr_content_for_diocese(diocese_key: str) -> tuple[str, bool]:
    viewer_path, _viewer_date = _latest_viewer(diocese_key)
    html_content = _ocr_html_from_viewer(viewer_path)
    if html_content:
        return html_content, True
    standalone = _latest_ocr_standalone(diocese_key)
    html_content = _ocr_html_from_standalone(standalone)
    if html_content:
        return html_content, True
    plain = _ocr_text_from_viewer(viewer_path)
    return plain, False


def _ocr_text_from_viewer(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    raw_html = path.read_text(encoding="utf-8")
    match = re.search(
        r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    fragment = match.group(1)
    without_tags = re.sub(r"<[^>]+>", "\n", fragment)
    compacted = re.sub(r"[ \t\r\f\v]+", " ", without_tags)
    lines = [line.strip() for line in compacted.splitlines() if line.strip()]
    return "\n".join(lines)


def _placeholder_page(diocese: DioceseCard, out_path: Path) -> None:
    parish_links = _parish_links(diocese.key)
    short = diocese.name.removesuffix(" Diocese").strip() or diocese.name
    parish_markup = ""
    if parish_links:
        parish_markup = f"""
    <section class="parish-section">
      <h2>Parish links</h2>
      {_render_placeholder_parish_links(parish_links)}
    </section>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(diocese.name)} Collated Bulletin — Parish Press</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
      background: #ffffff;
      color: #222222;
      line-height: 1.5;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 40px; }}
    h1 {{
      margin: 0 0 16px;
      padding: 0 0 16px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 1.5rem;
      font-weight: 600;
      color: #1e3a5f;
    }}
    .note {{ margin: 0 0 24px; color: #666666; font-size: 1rem; }}
    .parish-section h2 {{
      margin: 0 0 12px;
      font-size: 1.05rem;
      font-weight: 600;
      color: #1e3a5f;
    }}
    .parish-list {{ margin: 0; padding-left: 20px; columns: 2; column-gap: 28px; }}
    .parish-list li {{ margin: 6px 0; break-inside: avoid; }}
    .parish-list a {{ color: #1e3a5f; text-decoration: none; font-weight: 500; }}
    .parish-list a:hover {{ text-decoration: underline; }}
    @media (max-width: 520px) {{ .parish-list {{ columns: 1; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>{html.escape(short)} Collated Bulletin</h1>
    <p class="note">We're still collecting bulletins for this diocese. Check back next Sunday.</p>
{parish_markup}
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def _load_reliability() -> dict[str, dict]:
    if not RELIABILITY_PATH.exists():
        return {}
    try:
        payload = json.loads(RELIABILITY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    parishes = payload.get("parishes")
    return parishes if isinstance(parishes, dict) else {}


def _status_dot(avg_success_rate: float | None) -> str:
    if avg_success_rate is None:
        return "⚪"
    if avg_success_rate >= 0.8:
        return "🟢"
    if avg_success_rate >= 0.5:
        return "��"
    return "🔴"


def _landing_page(rows: list[dict[str, str]]) -> str:
    live_sections = "".join(
        (
            "<section class=\"live-diocese\">"
            f"<div class=\"live-diocese-head\"><h2>{html_name} Diocese</h2>"
            f"<a href=\"dioceses/{row['key']}/\">Open parish bulletins →</a></div>"
            "<p class=\"live-diocese-note\">Parish links below come from the bulletin evidence file.</p>"
            f"{_render_placeholder_parish_links(_parish_links(row['key']))}"
            "</section>"
        )
        for row in rows
        if row["key"] in LIVE_DIOCESES and _parish_links(row["key"])
        for html_name in [row["name"]]
    )
    cards_html = "".join(
        (
            "<article class=\"diocese-card\">"
            f"<h2>{row['name']}</h2>"
            f"<p><strong>{row['dot']}</strong> {row['status_label']}</p>"
            f"<p>Last updated: {row['updated']}</p>"
            f"<a href=\"dioceses/{row['key']}/\">Open →</a>"
            "</article>"
        )
        for row in rows
    )
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Parish Press — Irish Catholic Bulletins</title>
  <link rel=\"stylesheet\" href=\"assets/site.css\" />
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f7fbfb; color: #16202a; }}
    .hero {{ background: #1a6b6b; color: #fff; padding: 26px 18px; }}
    .hero-inner, .content, .footer {{ max-width: 1180px; margin: 0 auto; }}
    .banner {{ background: #fff4df; border: 1px solid #f5d08d; color: #704d0f; border-radius: 10px; padding: 10px 12px; margin-top: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-top: 18px; }}
    .diocese-card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 14px; }}
    .diocese-card h2 {{ margin: 0 0 8px; font-size: 1.08rem; }}
    .diocese-card p {{ margin: 0 0 8px; color: #4b5563; }}
    .diocese-card a {{ color: #1a6b6b; font-weight: 700; text-decoration: none; }}
    .diocese-card a:hover {{ text-decoration: underline; }}
    .content {{ padding: 20px 16px 10px; }}
    .live-diocese {{ margin-top: 20px; background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 16px; }}
    .live-diocese-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
    .live-diocese-head h2 {{ margin: 0; color: #1a6b6b; }}
    .live-diocese-head a {{ color: #1a6b6b; font-weight: 700; text-decoration: none; }}
    .live-diocese-head a:hover {{ text-decoration: underline; }}
    .live-diocese-note {{ margin: 8px 0 12px; color: #4b5563; }}
    .parish-list {{ margin: 0; padding-left: 18px; columns: 3; }}
    .parish-list li {{ margin: 6px 0; }}
    .parish-list a {{ color: #1a6b6b; text-decoration: none; }}
    .parish-list a:hover {{ text-decoration: underline; }}
    .footer {{ border-top: 1px solid #d6ecea; margin-top: 18px; padding: 14px 16px 24px; color: #4b5563; font-size: 0.95rem; }}
    .footer a {{ color: #1a6b6b; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <header class=\"hero\">
    <div class=\"hero-inner\">
      <h1>Parish Press — Irish Catholic Bulletins</h1>
      <p>Auto-collected every Sunday. Free forever.</p>
      <p class=\"banner\">🤖 Bulletins are auto-collected from parish websites. OCR may contain errors. Always check the original PDF.</p>
    </div>
  </header>
  <main class=\"content\">
    <section class=\"grid\">{cards_html}</section>
    {live_sections}
  </main>
  <footer class=\"footer\">
    <p><a href=\"bulletins/index.html\">Browse the full OCR bulletin archive</a></p>
    <p><a href=\"mega_pdf/index.html\">Open the Collated Bulletin PDF viewer</a></p>
    <p><a href=\"EMBEDDING.md\">Read the embedding guide</a> · <a href=\"embed-examples.html\">Open copy/paste embed examples</a></p>
    <p><a href=\"badges/\">Parish reliability scores</a></p>
    <p>Subscribe (RSS): <a href=\"feeds/derry_diocese.xml\">Derry Diocese</a> · <a href=\"feeds/down_and_connor.xml\">Down &amp; Connor</a></p>
    <p><a href=\"search/\">Search all bulletins</a></p>
    <p>📅 Subscribe in Google/Apple Calendar: <a href=\"calendars/derry.ics\">Derry Diocese</a> · <a href=\"calendars/down_and_connor.ics\">Down &amp; Connor</a> · <a href=\"calendars/all.ics\">All parishes</a></p>
    <p><a href=\"sitemap.html\">🗺️ Site map — every public URL</a> · <a href=\"COST_DASHBOARD.md\">💷 Cost dashboard</a></p>
    <p><a href=\"subscribe/\">📬 Subscribe for reminders</a></p>
    <p>© 2026 Parish Press</p>
  </footer>
</body>
</html>
"""


def _subscribe_page(dioceses: list[DioceseCard]) -> str:
    items = "".join(
        f'<li><a href="../dioceses/{d.key}/">{d.name}</a></li>' for d in dioceses
    )
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Subscribe — Parish Press</title>
  <link rel=\"stylesheet\" href=\"../assets/site.css\" />
</head>
<body>
  <main style=\"max-width:900px;margin:0 auto;padding:20px 16px;font-family:Arial,Helvetica,sans-serif;\">
    <h1>📬 Subscribe for reminders</h1>
    <p>Pick your diocese page below and use the RSS/calendar links from the footer.</p>
    <ul style=\"columns:2;\">{items}</ul>
  </main>
</body>
</html>
"""


def _bulletin_viewer_url(diocese_key: str) -> str:
    viewer_path, _viewer_date = _latest_viewer(diocese_key)
    if viewer_path is None:
        return "../../bulletins/index.html"
    return f"../../bulletins/{viewer_path.name}"


def _ocr_standalone_url(diocese_key: str) -> str:
    standalone = _latest_ocr_standalone(diocese_key)
    if standalone is not None:
        return f"../../bulletins/{standalone.name}"
    return _bulletin_viewer_url(diocese_key)


def _mega_pdf_url(diocese_key: str) -> str:
    stem = diocese_key.replace("-", "_")
    return f"../../mega_pdf/{stem}_mega_bulletin.pdf"


def _parish_links_for_big_bulletin(diocese_key: str, report_path: Path) -> list[dict[str, str]]:
    if diocese_key == "raphoe":
        return _parish_links(diocese_key)
    links, _stats = _parish_links_with_harvest(diocese_key, report_path)
    return [{"name": str(item.get("name") or ""), "url": str(item.get("url") or "")} for item in links if item.get("url")]


def _render_placeholder_parish_links(parish_links: list[dict[str, str]]) -> str:
    if not parish_links:
        return "<p>No parish links available yet.</p>"
    items = "".join(
        f'<li><a href="{html.escape(link["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(link["name"])}</a></li>'
        for link in sorted(parish_links, key=lambda item: item["name"].lower())
    )
    return f'<ul class="parish-list">{items}</ul>'


def run(report_path: Path = REPORT_PATH, docs_dir: Path = DOCS_DIR) -> None:
    dioceses = _all_dioceses()
    downloaded = _load_downloaded(report_path)
    reliability = _load_reliability()
    _downloaded_map, _failed_map, _skipped_map, target_date = _load_report_sections(report_path)
    from harvester.utils import format_uk_date

    week_label = format_uk_date(target_date) or target_date or "this Sunday"

    rows: list[dict[str, str]] = []
    for diocese in dioceses:
        out_path = docs_dir / "dioceses" / diocese.key / "index.html"
        keys = _recipe_keys(diocese.key)
        trained = bool(keys)
        success_this_run = bool(downloaded.intersection(keys))

        if diocese.key in LIVE_DIOCESES and trained:
            parish_links = _parish_links_for_big_bulletin(diocese.key, report_path)
            ocr_text, ocr_is_html = _ocr_content_for_diocese(diocese.key)
            display_short = diocese.name.removesuffix(" Diocese").strip() or diocese.name
            render_diocese_raphoe_page(
                parish_links=parish_links,
                out_path=out_path,
                mega_pdf_url=_mega_pdf_url(diocese.key),
                bulletin_viewer_url=_bulletin_viewer_url(diocese.key),
                ocr_standalone_url=_ocr_standalone_url(diocese.key),
                ocr_text=ocr_text,
                ocr_is_html=ocr_is_html,
                week_label=week_label if target_date else "",
                diocese_display_name=diocese.name,
                headline=f"{display_short} Collated Bulletin",
                parish_heading="Working parish links",
            )
            updated_label = format_uk_date(target_date) or target_date or "Coming soon"
        else:
            _placeholder_page(diocese, out_path)
            updated_label = "Coming soon"

        rates = []
        for key in keys:
            value = reliability.get(key)
            if isinstance(value, dict):
                rate = value.get("success_rate")
                if isinstance(rate, (int, float)):
                    rates.append(float(rate))
        avg = (sum(rates) / len(rates)) if rates else None
        dot = _status_dot(avg)
        status_label = "Reliability available" if avg is not None else "No reliability data yet"
        rows.append(
            {
                "key": diocese.key,
                "name": diocese.name,
                "dot": dot,
                "status_label": status_label,
                "updated": updated_label,
            }
        )

    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(_landing_page(rows), encoding="utf-8")
    subscribe_dir = docs_dir / "subscribe"
    subscribe_dir.mkdir(parents=True, exist_ok=True)
    (subscribe_dir / "index.html").write_text(_subscribe_page(dioceses), encoding="utf-8")
