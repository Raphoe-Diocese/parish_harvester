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
# site_builder uses hyphenated diocese keys; ocr.generate_bulletin_pages /
# ocr.parish_pages use the underscored keys from parishes/dioceses.json.
OCR_DIOCESE_KEYS = {"raphoe": "raphoe", "derry": "derry", "down-and-connor": "down_and_connor"}
RELIABILITY_PATH = DOCS_DIR / "reliability.json"
REPORT_PATH = REPO_ROOT / "Bulletins" / "report.json"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Raphoe-Diocese/parish_harvester/main/Bulletins/current"
EVIDENCE_DIOCESE_KEYS = {
    "derry": "derry_diocese",
    "down-and-connor": "down_and_connor",
    "raphoe": "raphoe_diocese",
}

@dataclass(frozen=True)
class HeroSlide:
    """One slide of the homepage hero slider.

    Set ``image`` to a photo URL (a full ``https://`` URL, e.g. a Wikimedia
    Commons hotlink, or a path relative to ``docs/`` such as
    ``"assets/hero/slide-1.jpg"`` for a locally-hosted file) to use a real
    photo instead of the CSS gradient placeholder — see
    ``docs/assets/hero/README.md`` for details. Frank can swap these in
    without touching any generated HTML.

    ``credit`` is the small on-image attribution line legally required by
    CC-licensed photos (e.g. ``"Photo: Jane Doe / Wikimedia Commons / CC
    BY-SA 4.0"``) — leave as ``None`` for public-domain images or your own
    photos that need no credit.

    ``position`` is a CSS ``background-position`` value (default
    ``"center"``) — useful for tall/portrait source photos where the
    interesting part (e.g. cathedral spires) isn't in the vertical middle.
    """

    gradient: str
    eyebrow: str
    title: str
    subtitle: str
    image: str | None = None
    credit: str | None = None
    position: str = "center"


# Cathedral photos for the 3 live dioceses, sourced from Wikimedia Commons
# (all confirmed Creative Commons licensed on their individual file pages —
# see the "Photo credits" section of docs/assets/hero/README.md for the
# full license/author/source details for each). Falls back to a CSS
# gradient automatically if `image` is ever cleared — see HeroSlide above
# and docs/assets/hero/README.md for how to swap any of these out.
HERO_SLIDES: list[HeroSlide] = [
    HeroSlide(
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/"
            "Letterkenny_-_Cathedral_of_St._Eunan_and_St._Columba_-_20190421142600.jpg/"
            "1280px-Letterkenny_-_Cathedral_of_St._Eunan_and_St._Columba_-_20190421142600.jpg"
        ),
        credit="Photo: Dieglop / Wikimedia Commons / CC BY-SA 4.0",
        gradient="linear-gradient(135deg, #0f3d3d 0%, #1a6b6b 55%, #3fae9a 100%)",
        eyebrow="Raphoe Diocese",
        title="Cathedral of St. Eunan and St. Columba, Letterkenny",
        subtitle="Auto-collected every Sunday, free forever.",
    ),
    HeroSlide(
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/"
            "Derry_St._Eugene%27s_Cathedral_2019_09_29.jpg/"
            "1280px-Derry_St._Eugene%27s_Cathedral_2019_09_29.jpg"
        ),
        credit="Photo: Andreas F. Borchert / Wikimedia Commons / CC BY-SA 4.0",
        gradient="linear-gradient(135deg, #1f2f52 0%, #35508f 55%, #6f8fd4 100%)",
        eyebrow="Derry Diocese",
        title="St Eugene's Cathedral, Derry",
        subtitle="Full PDF viewer and searchable OCR text for every bulletin we collect.",
    ),
    HeroSlide(
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/"
            "BELFAST%2C_St_Peter%27s_Cathedral_Ext_%2851103078079%29.jpg/"
            "1280px-BELFAST%2C_St_Peter%27s_Cathedral_Ext_%2851103078079%29.jpg"
        ),
        credit="Photo: The National Churches Trust / Wikimedia Commons / CC BY 2.0",
        position="center 35%",
        gradient="linear-gradient(135deg, #4a2545 0%, #7a3b66 55%, #c47a9a 100%)",
        eyebrow="Down & Connor Diocese",
        title="St Peter's Cathedral, Belfast",
        subtitle="Works on any phone, tablet or computer. Subscribe by RSS or calendar if you'd like a nudge.",
    ),
]


def _hero_slider_html() -> str:
    if not HERO_SLIDES:
        return ""
    slides_html = []
    dots_html = []
    for i, slide in enumerate(HERO_SLIDES):
        bg = (
            f"linear-gradient(180deg, rgba(10,20,20,0.15) 0%, rgba(10,20,20,0.72) 100%), "
            f"url('{html.escape(slide.image, quote=True)}') {slide.position}/cover no-repeat"
            if slide.image
            else slide.gradient
        )
        active = " is-active" if i == 0 else ""
        credit_html = (
            f'<p class="hero-slide-credit">{html.escape(slide.credit)}</p>' if slide.credit else ""
        )
        slides_html.append(
            f'<div class="hero-slide{active}" style="background:{bg};" '
            f'role="group" aria-roledescription="slide" aria-label="{i + 1} of {len(HERO_SLIDES)}" '
            f'aria-hidden="{"false" if i == 0 else "true"}">'
            f'<p class="hero-slide-eyebrow">{html.escape(slide.eyebrow)}</p>'
            f'<h1 class="hero-slide-title">{html.escape(slide.title)}</h1>'
            f'<p class="hero-slide-subtitle">{html.escape(slide.subtitle)}</p>'
            f"{credit_html}"
            "</div>"
        )
        dots_html.append(
            f'<button type="button" class="hero-dot{" is-active" if i == 0 else ""}" '
            f'data-slide-index="{i}" aria-label="Go to slide {i + 1}"></button>'
        )
    controls = (
        '<button type="button" class="hero-nav hero-prev" aria-label="Previous slide">&#8249;</button>'
        '<button type="button" class="hero-nav hero-next" aria-label="Next slide">&#8250;</button>'
        if len(HERO_SLIDES) > 1
        else ""
    )
    dots = f'<div class="hero-dots">{"".join(dots_html)}</div>' if len(HERO_SLIDES) > 1 else ""
    return f"""<section class="hero-slider" data-hero-slider aria-roledescription="carousel" aria-label="Featured">
    <div class="hero-slider-track">{"".join(slides_html)}</div>
    {controls}
    {dots}
  </section>"""


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


def _normalise_parish_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _internal_parish_hrefs(diocese_key: str, docs_dir: Path) -> dict[str, str]:
    """normalised parish name -> this diocese's own per-parish page href.

    Parish pages are generated by ``ocr.parish_pages`` during the OCR
    workflow step (see ``ocr.generate_bulletin_pages.write_viewer_page``),
    which runs before this module rebuilds the diocese "current" pages —
    so by the time this looks, any page for a currently-"ok" parish already
    exists on disk under ``{docs_dir}/parishes/{diocese_key}/``.
    """
    ocr_key = OCR_DIOCESE_KEYS.get(diocese_key)
    if not ocr_key:
        return {}
    try:
        from ocr.parish_pages import load_ok_parishes
    except Exception:
        return {}
    parish_pages_dir = docs_dir / "parishes" / ocr_key
    parish_status_path = REPO_ROOT / "parishes" / "parish_status.json"
    hrefs: dict[str, str] = {}
    for parish in load_ok_parishes(ocr_key, parish_status_path=parish_status_path):
        if (parish_pages_dir / f"{parish.key}.html").exists():
            hrefs[_normalise_parish_name(parish.display_name)] = (
                f"../../parishes/{ocr_key}/{parish.key}.html"
            )
    return hrefs


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
        return "🟡"
    return "🔴"


def _landing_page(rows: list[dict[str, str]]) -> str:
    """Homepage: the 3 live dioceses prominent up top, the other 23 collapsed.

    Only Raphoe, Derry and Down & Connor have real reliability data today
    (see ``LIVE_DIOCESES``), so they get full cards with one-click links to
    their collated (mega) bulletin and text bulletin. Every other diocese —
    still "coming soon" — collapses into one small expandable list instead of
    23 near-empty placeholder cards, entirely driven by the same per-diocese
    rows (dot/status/updated) computed in :func:`run`.
    """
    live_rows = [row for row in rows if row["key"] in LIVE_DIOCESES]
    other_rows = sorted(
        (row for row in rows if row["key"] not in LIVE_DIOCESES),
        key=lambda row: row["name"],
    )

    live_cards_html = "".join(
        (
            "<article class=\"live-card\">"
            f"<p class=\"live-card-eyebrow\">{row['dot']} {html.escape(row['status_label'])}</p>"
            f"<h2>{html.escape(row['name'])} Diocese</h2>"
            f"<p class=\"live-card-updated\">Last updated: {html.escape(row['updated'])}</p>"
            "<div class=\"live-card-actions\">"
            f"<a class=\"live-btn primary\" href=\"dioceses/{row['key']}/\" target=\"_blank\" rel=\"noopener noreferrer\">Open Collated Bulletin →</a>"
            f"<a class=\"live-btn secondary\" href=\"{html.escape(_mega_pdf_url(row['key']), quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">📄 Mega PDF</a>"
            f"<a class=\"live-btn secondary\" href=\"{html.escape(_ocr_standalone_url(row['key']), quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">📝 Text Bulletin</a>"
            "</div>"
            "</article>"
        )
        for row in live_rows
    )

    other_rows_html = "".join(
        f"<li>{row['dot']} <a href=\"dioceses/{row['key']}/\" target=\"_blank\" rel=\"noopener noreferrer\">{html.escape(row['name'])}</a></li>"
        for row in other_rows
    )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Parish Press — Irish Catholic Bulletins</title>
  <link rel=\"stylesheet\" href=\"assets/site.css\" />
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, Helvetica, sans-serif;
      background: #f5f8f8;
      color: #16202a;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: #1a6b6b; }}
    .topbar {{ background: #0f2f2f; color: #eafaf7; padding: 12px 18px; }}
    .topbar-inner, .content, .footer {{ max-width: 1180px; margin: 0 auto; }}
    .topbar-inner {{ display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 4px 16px; }}
    .brand {{ font-weight: 800; font-size: 1.05rem; letter-spacing: 0.01em; }}
    .brand span {{ opacity: 0.75; font-weight: 500; }}
    .topbar-tagline {{ margin: 0; font-size: 0.85rem; color: #b9dfd9; }}

    /* Hero image/gradient slider */
    .hero-slider {{
      position: relative;
      overflow: hidden;
      height: min(52vw, 360px);
      min-height: 220px;
      background: #0f2f2f;
    }}
    .hero-slider-track {{ position: relative; width: 100%; height: 100%; }}
    .hero-slide {{
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      gap: 6px;
      padding: 22px 20px 30px;
      opacity: 0;
      transition: opacity 900ms ease;
      color: #fff;
    }}
    .hero-slide.is-active {{ opacity: 1; z-index: 1; }}
    .hero-slide-eyebrow {{ margin: 0; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #d8f3ee; text-shadow: 0 1px 3px rgba(0,0,0,0.35); }}
    .hero-slide-title {{ margin: 0; font-size: clamp(1.4rem, 4vw, 2.35rem); line-height: 1.15; font-weight: 800; max-width: 46rem; text-shadow: 0 2px 8px rgba(0,0,0,0.35); }}
    .hero-slide-subtitle {{ margin: 0; font-size: clamp(0.9rem, 1.6vw, 1.05rem); color: #eef7f5; max-width: 40rem; text-shadow: 0 1px 4px rgba(0,0,0,0.35); }}
    .hero-slide-credit {{ position: absolute; right: 10px; bottom: 8px; margin: 0; font-size: 0.7rem; color: rgba(255,255,255,0.85); text-shadow: 0 1px 3px rgba(0,0,0,0.6); }}
    .hero-nav {{
      position: absolute; top: 50%; transform: translateY(-50%);
      width: 38px; height: 38px; border-radius: 999px; border: none;
      background: rgba(10, 25, 25, 0.38); color: #fff; font-size: 1.4rem; line-height: 1;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      z-index: 2; transition: background 150ms ease;
    }}
    .hero-nav:hover {{ background: rgba(10, 25, 25, 0.6); }}
    .hero-prev {{ left: 12px; }}
    .hero-next {{ right: 12px; }}
    .hero-dots {{ position: absolute; left: 0; right: 0; bottom: 10px; z-index: 2; display: flex; justify-content: center; gap: 7px; }}
    .hero-dot {{ width: 8px; height: 8px; padding: 0; border-radius: 999px; border: none; background: rgba(255,255,255,0.45); cursor: pointer; }}
    .hero-dot.is-active {{ background: #fff; width: 20px; }}
    .hero-dot {{ transition: width 200ms ease, background 200ms ease; }}
    @media (prefers-reduced-motion: reduce) {{
      .hero-slide {{ transition: none; }}
      .hero-dot {{ transition: none; }}
    }}

    .intro {{ padding: 22px 16px 4px; text-align: center; }}
    .intro p {{ margin: 0 auto; max-width: 46rem; color: #45565f; font-size: 1.02rem; line-height: 1.5; }}
    .banner {{ background: #fff4df; border: 1px solid #f5d08d; color: #704d0f; border-radius: 10px; padding: 10px 14px; margin: 14px auto 0; max-width: 46rem; font-size: 0.9rem; }}

    .content {{ padding: 22px 16px 10px; }}
    .section-title {{ margin: 8px 0 14px; font-size: 0.92rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: #4b5563; }}
    .live-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 18px; }}
    .live-card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 16px; padding: 20px; box-shadow: 0 8px 22px rgba(15, 47, 47, 0.07); transition: transform 150ms ease, box-shadow 150ms ease; }}
    .live-card:hover {{ transform: translateY(-2px); box-shadow: 0 12px 28px rgba(15, 47, 47, 0.11); }}
    .live-card-eyebrow {{ margin: 0 0 8px; font-size: 0.8rem; font-weight: 700; color: #4b5563; text-transform: uppercase; letter-spacing: 0.04em; }}
    .live-card h2 {{ margin: 0 0 6px; font-size: 1.35rem; color: #114b4b; }}
    .live-card-updated {{ margin: 0 0 16px; color: #6b7686; font-size: 0.88rem; }}
    .live-card-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .live-btn {{ display: inline-flex; align-items: center; padding: 9px 14px; border-radius: 8px; font-weight: 700; font-size: 0.9rem; text-decoration: none; }}
    .live-btn.primary {{ background: #1a6b6b; color: #fff; }}
    .live-btn.secondary {{ background: #eef8f7; color: #1a6b6b; border: 1px solid #cfe8e6; }}
    .live-btn:hover {{ opacity: 0.92; text-decoration: none; }}
    .more-dioceses {{ margin-top: 28px; background: #fff; border: 1px solid #d6ecea; border-radius: 14px; padding: 16px 20px; }}
    .more-dioceses summary {{ cursor: pointer; font-weight: 700; color: #1a6b6b; list-style: none; }}
    .more-dioceses summary::-webkit-details-marker {{ display: none; }}
    .more-dioceses summary::before {{ content: "▸ "; }}
    .more-dioceses[open] summary::before {{ content: "▾ "; }}
    .more-dioceses-note {{ margin: 10px 0 12px; color: #6b7280; font-size: 0.88rem; }}
    .more-dioceses-grid {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 6px 16px; }}
    .more-dioceses-grid li {{ margin: 0; font-size: 0.92rem; }}
    .more-dioceses-grid a {{ color: #375569; text-decoration: none; }}
    .more-dioceses-grid a:hover {{ text-decoration: underline; color: #1a6b6b; }}
    .footer {{ border-top: 1px solid #d6ecea; margin-top: 28px; padding: 16px 16px 28px; color: #5a6672; font-size: 0.92rem; line-height: 1.8; }}
    .footer a {{ color: #1a6b6b; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
    @media (max-width: 640px) {{
      .live-btn {{ flex: 1 1 auto; justify-content: center; }}
      .hero-nav {{ width: 32px; height: 32px; font-size: 1.2rem; }}
    }}
  </style>
</head>
<body>
  <div class=\"topbar\">
    <div class=\"topbar-inner\">
      <div class=\"brand\">Parish Press <span>· Irish Catholic Bulletins</span></div>
      <p class=\"topbar-tagline\">Auto-collected every Sunday. Free forever.</p>
    </div>
  </div>
  {_hero_slider_html()}
  <main class=\"content\">
    <div class=\"intro\">
      <p>Every week we automatically fetch each parish's bulletin, stitch them into one collated PDF per diocese, and make the text searchable — so you can read your parish notices without hunting through a website.</p>
      <p class=\"banner\">🤖 Bulletins are auto-collected from parish websites. OCR may contain errors. Always check the original PDF.</p>
    </div>
    <p class=\"section-title\">Live dioceses</p>
    <section class=\"live-grid\">{live_cards_html}</section>
    <details class=\"more-dioceses\">
      <summary>More dioceses — coming soon ({len(other_rows)})</summary>
      <p class=\"more-dioceses-note\">These dioceses don't have reliability data yet. Tap a name to see what's available so far.</p>
      <ul class=\"more-dioceses-grid\">{other_rows_html}</ul>
    </details>
  </main>
  <footer class=\"footer\">
    <p><a href=\"bulletins/index.html\" target=\"_blank\" rel=\"noopener noreferrer\">Browse the full OCR bulletin archive</a></p>
    <p><a href=\"mega_pdf/index.html\" target=\"_blank\" rel=\"noopener noreferrer\">Open the Collated Bulletin PDF viewer</a></p>
    <p><a href=\"EMBEDDING.md\" target=\"_blank\" rel=\"noopener noreferrer\">Read the embedding guide</a> · <a href=\"embed-examples.html\" target=\"_blank\" rel=\"noopener noreferrer\">Open copy/paste embed examples</a></p>
    <p><a href=\"badges/\" target=\"_blank\" rel=\"noopener noreferrer\">Parish reliability scores</a></p>
    <p>Subscribe (RSS): <a href=\"feeds/derry_diocese.xml\" target=\"_blank\" rel=\"noopener noreferrer\">Derry Diocese</a> · <a href=\"feeds/down_and_connor.xml\" target=\"_blank\" rel=\"noopener noreferrer\">Down &amp; Connor</a></p>
    <p><a href=\"search/\" target=\"_blank\" rel=\"noopener noreferrer\">Search all bulletins</a></p>
    <p>📅 Subscribe in Google/Apple Calendar: <a href=\"calendars/derry.ics\" target=\"_blank\" rel=\"noopener noreferrer\">Derry Diocese</a> · <a href=\"calendars/down_and_connor.ics\" target=\"_blank\" rel=\"noopener noreferrer\">Down &amp; Connor</a> · <a href=\"calendars/all.ics\" target=\"_blank\" rel=\"noopener noreferrer\">All parishes</a></p>
    <p><a href=\"sitemap.html\" target=\"_blank\" rel=\"noopener noreferrer\">🗺️ Site map — every public URL</a> · <a href=\"COST_DASHBOARD.md\" target=\"_blank\" rel=\"noopener noreferrer\">💷 Cost dashboard</a></p>
    <p><a href=\"subscribe/\" target=\"_blank\" rel=\"noopener noreferrer\">📬 Subscribe for reminders</a></p>
    <p>© 2026 Parish Press</p>
  </footer>
  <script>
  (function () {{
    var slider = document.querySelector('[data-hero-slider]');
    if (!slider) return;
    var slides = Array.prototype.slice.call(slider.querySelectorAll('.hero-slide'));
    var dots = Array.prototype.slice.call(slider.querySelectorAll('.hero-dot'));
    if (slides.length < 2) return;

    var current = 0;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var AUTO_ADVANCE_MS = 6000;
    var timer = null;

    function show(index) {{
      current = (index + slides.length) % slides.length;
      slides.forEach(function (slide, i) {{
        var active = i === current;
        slide.classList.toggle('is-active', active);
        slide.setAttribute('aria-hidden', active ? 'false' : 'true');
      }});
      dots.forEach(function (dot, i) {{
        dot.classList.toggle('is-active', i === current);
      }});
    }}

    function next() {{ show(current + 1); }}
    function prev() {{ show(current - 1); }}

    function startAuto() {{
      if (reduceMotion) return;
      stopAuto();
      timer = window.setInterval(next, AUTO_ADVANCE_MS);
    }}
    function stopAuto() {{
      if (timer) {{ window.clearInterval(timer); timer = null; }}
    }}

    var prevBtn = slider.querySelector('.hero-prev');
    var nextBtn = slider.querySelector('.hero-next');
    if (prevBtn) prevBtn.addEventListener('click', function () {{ prev(); startAuto(); }});
    if (nextBtn) nextBtn.addEventListener('click', function () {{ next(); startAuto(); }});
    dots.forEach(function (dot, i) {{
      dot.addEventListener('click', function () {{ show(i); startAuto(); }});
    }});

    slider.addEventListener('mouseenter', stopAuto);
    slider.addEventListener('mouseleave', startAuto);
    slider.addEventListener('focusin', stopAuto);
    slider.addEventListener('focusout', startAuto);

    startAuto();
  }})();
  </script>
</body>
</html>
"""


def _subscribe_page(dioceses: list[DioceseCard]) -> str:
    items = "".join(
        f'<li><a href="../dioceses/{d.key}/" target="_blank" rel="noopener noreferrer">{d.name}</a></li>' for d in dioceses
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


def _ocr_standalone_url(diocese_key: str) -> str:
    standalone = _latest_ocr_standalone(diocese_key)
    pages_base = "https://raphoe-diocese.github.io/parish_harvester"
    if standalone is not None:
        return f"{pages_base}/bulletins/{standalone.name}"
    viewer_path, _viewer_date = _latest_viewer(diocese_key)
    if viewer_path is not None:
        return f"{pages_base}/bulletins/{viewer_path.name}"
    return f"{pages_base}/bulletins/index.html"


def _mega_pdf_url(diocese_key: str) -> str:
    stem = diocese_key.replace("-", "_")
    pages_base = "https://raphoe-diocese.github.io/parish_harvester"
    return f"{pages_base}/mega_pdf/{stem}_mega_bulletin.pdf"


def _latest_pdf_standalone(diocese_key: str) -> Path | None:
    """Latest distraction-free PDF-only page (`{diocese}-{date}-pdf.html`)."""
    if not BULLETINS_DIR.exists():
        return None
    stem = diocese_key.replace("-", "[-_]")
    regex = re.compile(rf"^{stem}-(\d{{4}}-\d{{2}}-\d{{2}})-pdf\.html$")
    latest: tuple[Path, str] | None = None
    for path in sorted(BULLETINS_DIR.glob("*.html")):
        match = regex.match(path.name)
        if not match:
            continue
        date_text = match.group(1)
        if latest is None or date_text > latest[1]:
            latest = (path, date_text)
    return latest[0] if latest else None


def _pdf_standalone_url(diocese_key: str) -> str:
    standalone = _latest_pdf_standalone(diocese_key)
    pages_base = "https://raphoe-diocese.github.io/parish_harvester"
    if standalone is not None:
        return f"{pages_base}/bulletins/{standalone.name}"
    return _mega_pdf_url(diocese_key)


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
            if display_short == "Down and Connor":
                display_short = "Down & Connor"
            render_diocese_raphoe_page(
                parish_links=parish_links,
                out_path=out_path,
                mega_pdf_url=_mega_pdf_url(diocese.key),
                ocr_standalone_url=_ocr_standalone_url(diocese.key),
                pdf_standalone_url=_pdf_standalone_url(diocese.key),
                ocr_text=ocr_text,
                ocr_is_html=ocr_is_html,
                week_label=week_label if target_date else "",
                diocese_display_name=diocese.name,
                headline=f"{display_short} Collated Bulletin",
                internal_parish_hrefs=_internal_parish_hrefs(diocese.key, docs_dir),
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
