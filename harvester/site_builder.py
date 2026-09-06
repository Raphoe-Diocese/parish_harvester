from __future__ import annotations

import json
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from harvester.diocese_intro import (
    DioceseWeekSummary,
    build_diocese_week_summary,
    load_mega_page_index,
    render_diocese_intro_html,
)
from harvester.fetcher import parse_evidence_file
from harvester.page_renderer import (
    render_diocese_raphoe_page,
)
from harvester.parish_aliases import (
    collapse_named_links,
    combined_display_name,
    is_alias_key,
    name_lookup_keys,
)
from harvester.site_chrome import favicon_link_tags, scroll_top_css, scroll_top_html, scroll_top_js
from ocr.generate_bulletin_pages import with_mega_pdf_week

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
RECIPES_DIR = REPO_ROOT / "parishes" / "recipes"
BULLETINS_DIR = DOCS_DIR / "bulletins"

LIVE_DIOCESES = {"raphoe", "derry", "down-and-connor", "clogher"}
# site_builder uses hyphenated diocese keys; ocr.generate_bulletin_pages /
# ocr.parish_pages use the underscored keys from parishes/dioceses.json.
OCR_DIOCESE_KEYS = {"raphoe": "raphoe", "derry": "derry", "down-and-connor": "down_and_connor", "clogher": "clogher"}
RELIABILITY_PATH = DOCS_DIR / "reliability.json"
REPORT_PATH = REPO_ROOT / "Bulletins" / "report.json"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Raphoe-Diocese/parish_harvester/main/Bulletins/current"
EVIDENCE_DIOCESE_KEYS = {
    "clogher": "clogher_diocese",
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
    diocese_key: str = ""
    image: str | None = None
    credit: str | None = None
    position: str = "center"


# Cathedral photos for the live dioceses, sourced from Wikimedia Commons.
# On-image credits stay off the hero (they clutter the photo). Attribution
# is kept on each slide record and shown once in a tiny homepage footer.
HERO_SLIDES: list[HeroSlide] = [
    HeroSlide(
        diocese_key="raphoe",
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/"
            "Letterkenny_-_Cathedral_of_St._Eunan_and_St._Columba_-_20190421142600.jpg/"
            "1280px-Letterkenny_-_Cathedral_of_St._Eunan_and_St._Columba_-_20190421142600.jpg"
        ),
        credit="Photo: Dieglop / Wikimedia Commons / CC BY-SA 4.0",
        gradient="linear-gradient(135deg, #0f3d3d 0%, #1a6b6b 55%, #3fae9a 100%)",
        eyebrow="Raphoe Diocese",
        title="Cathedral of St. Eunan and St. Columba, Letterkenny",
        subtitle="This week's parish bulletins, in one place.",
    ),
    HeroSlide(
        diocese_key="derry",
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/"
            "Derry_St._Eugene%27s_Cathedral_2019_09_29.jpg/"
            "1280px-Derry_St._Eugene%27s_Cathedral_2019_09_29.jpg"
        ),
        credit="Photo: Andreas F. Borchert / Wikimedia Commons / CC BY-SA 4.0",
        gradient="linear-gradient(135deg, #1f2f52 0%, #35508f 55%, #6f8fd4 100%)",
        eyebrow="Derry Diocese",
        title="St Eugene's Cathedral, Derry",
        subtitle="Read the PDF or the searchable text.",
    ),
    HeroSlide(
        diocese_key="down-and-connor",
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
        subtitle="Works on any phone, tablet or computer.",
    ),
    HeroSlide(
        diocese_key="clogher",
        image=(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/"
            "St_Macartans_Cathedral_Monaghan_Ireland.jpg/"
            "1280px-St_Macartans_Cathedral_Monaghan_Ireland.jpg"
        ),
        credit="Photo: Whoisjohngalt / Wikimedia Commons / CC BY-SA 4.0",
        position="center 30%",
        gradient="linear-gradient(135deg, #2c2416 0%, #6b5428 55%, #c4a15a 100%)",
        eyebrow="Clogher Diocese",
        title="St Macartan's Cathedral, Monaghan",
        subtitle="The mother church of Clogher.",
    ),
]


def _slide_for_diocese(diocese_key: str) -> HeroSlide | None:
    for slide in HERO_SLIDES:
        if slide.diocese_key == diocese_key:
            return slide
    return None


def _photo_credit_line() -> str:
    credits = [slide.credit for slide in HERO_SLIDES if slide.credit]
    if not credits:
        return ""
    return "Cathedral photos: Wikimedia Commons (CC BY / CC BY-SA)."


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
        slides_html.append(
            f'<div class="hero-slide{active}" style="background:{bg};" '
            f'role="group" aria-roledescription="slide" aria-label="{i + 1} of {len(HERO_SLIDES)}" '
            f'aria-hidden="{"false" if i == 0 else "true"}">'
            f'<p class="hero-slide-eyebrow">{html.escape(slide.eyebrow)}</p>'
            f'<h1 class="hero-slide-title">{html.escape(slide.title)}</h1>'
            f'<p class="hero-slide-subtitle">{html.escape(slide.subtitle)}</p>'
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
            collapsed = collapse_named_links(
                [
                    (entry.display_name, entry.bulletin_page or entry.example_url)
                    for entry in entries
                    if (entry.bulletin_page or entry.example_url)
                    and not is_alias_key(entry.key)
                ]
            )
            return [{"name": name, "url": url} for name, url in collapsed]

    links: list[dict[str, str]] = []
    for path in _recipe_files(diocese_key):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        key = str(payload.get("parish_key") or path.stem).strip()
        if is_alias_key(key):
            continue
        name = (
            combined_display_name(key)
            or str(payload.get("parish_name") or "").strip()
            or str(payload.get("display_name") or "").strip()
            or path.stem.replace("-", " ").replace("_", " ").title()
        )
        url = str(payload.get("start_url") or "").strip()
        if not url:
            continue
        links.append({"name": name, "url": url})
    return [{"name": name, "url": url} for name, url in collapse_named_links(
        [(item["name"], item["url"]) for item in links]
    )]


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
        if is_alias_key(key) or key in seen:
            return
        seen.add(key)
        name = combined_display_name(key) or name
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
            href = f"../../parishes/{ocr_key}/{parish.key}.html"
            labels = [parish.display_name, combined_display_name(parish.key) or ""]
            for label in labels:
                for token in name_lookup_keys(label):
                    hrefs[token] = href
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
  {favicon_link_tags()}
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


def _status_label(avg_success_rate: float | None) -> str:
    """Keep homepage card status on one line so the four cards stay level."""
    if avg_success_rate is None:
        return "No data yet"
    return "Reliability available"


# Public ready-by time on diocese cards (Irish clock). Harvest cron is 10:00 IST;
# Frank asked for 16:00 as the time readers should expect the week's set.
BULLETINS_READY_AT = "16:00"


def _ready_count_text(ready: int | None, total: int | None) -> str:
    """Honest this-week count. None means we do not know yet — do not invent."""
    if ready is None or total is None:
        return "—/—"
    return f"{ready}/{total}"


def _card_counts_from_summary(
    summary: DioceseWeekSummary | None,
) -> tuple[int | None, int | None]:
    """Use the same week summary as the diocese intro. total==0 stays unknown."""
    if summary is None or summary.total <= 0:
        return None, None
    return summary.found, summary.total


def _count_dot(ready: int | None, total: int | None) -> str:
    if ready is None or total is None or total <= 0:
        return "⚪"
    return _status_dot(ready / total)


def _live_card_ready_html(row: dict) -> str:
    raw_ready = row.get("ready_count")
    raw_total = row.get("total_count")
    ready = raw_ready if isinstance(raw_ready, int) else None
    total = raw_total if isinstance(raw_total, int) else None
    count = _ready_count_text(ready, total)
    dot = _count_dot(ready, total)
    return (
        "<p class=\"live-card-eyebrow\">"
        f"<span class=\"live-card-ready\">{dot} Bulletins ready @ {html.escape(BULLETINS_READY_AT)}</span>"
        f"<span class=\"live-card-count\">{html.escape(count)} available</span>"
        "</p>"
    )


_LONG_NAME_CHARS = 20
_VERY_LONG_NAME_CHARS = 28


def _short_diocese_name(name: str) -> str:
    short = name.removesuffix(" Diocese").strip()
    short = short.replace("-and-", " & ").replace(" and ", " & ")
    return re.sub(r"\s+", " ", short).strip()


def _length_class(label: str) -> str:
    n = len(label)
    if n >= _VERY_LONG_NAME_CHARS:
        return "is-very-long"
    if n >= _LONG_NAME_CHARS:
        return "is-long"
    return ""


def _live_card_heading(name: str) -> str:
    return f"{_short_diocese_name(name)} Diocese"


def _live_card_heading_html(name: str) -> str:
    heading = _live_card_heading(name)
    css = _length_class(heading)
    attr = f' class="{css}"' if css else ""
    return f"<h2{attr}>{html.escape(heading)}</h2>"


def _coming_soon_item_html(row: dict[str, str]) -> str:
    label = _short_diocese_name(row["name"])
    css = _length_class(label)
    attr = f' class="{css}"' if css else ""
    return (
        f"<li{attr}>{row['dot']} "
        f"<a href=\"dioceses/{row['key']}/\" target=\"_blank\" rel=\"noopener noreferrer\">"
        f"{html.escape(label)}</a></li>"
    )


def _landing_page(rows: list[dict[str, str]]) -> str:
    """Homepage: live dioceses prominent up top, the rest collapsed.

    Raphoe, Derry, Down & Connor and Clogher are in ``LIVE_DIOCESES``, so they
    get full cards with one-click links to their collated (mega) bulletin and
    text bulletin. Every other diocese — still "coming soon" — collapses into
    one small expandable list instead of near-empty placeholder cards,
    entirely driven by the same per-diocese rows (dot/status/updated)
    computed in :func:`run`.
    """
    live_rows = [row for row in rows if row["key"] in LIVE_DIOCESES]
    other_rows = sorted(
        (row for row in rows if row["key"] not in LIVE_DIOCESES),
        key=lambda row: row["name"],
    )

    def _live_card(row: dict[str, str]) -> str:
        slide = _slide_for_diocese(row["key"])
        if slide and slide.image:
            photo = (
                f"<div class=\"live-card-photo\" role=\"img\" "
                f"aria-label=\"{html.escape(slide.title, quote=True)}\" "
                f"style=\"background:url('{html.escape(slide.image, quote=True)}') "
                f"{html.escape(slide.position, quote=True)}/cover no-repeat;\"></div>"
            )
        else:
            photo = "<div class=\"live-card-photo live-card-photo-empty\" aria-hidden=\"true\"></div>"
        return (
            "<article class=\"live-card\">"
            f"{photo}"
            "<div class=\"live-card-body\">"
            f"{_live_card_ready_html(row)}"
            f"{_live_card_heading_html(row['name'])}"
            f"<p class=\"live-card-updated\">Updated {html.escape(row['updated'])}</p>"
            "<div class=\"live-card-actions\">"
            f"<a class=\"live-btn primary\" href=\"dioceses/{row['key']}/\">Open bulletin</a>"
            f"<a class=\"live-btn secondary\" href=\"{html.escape(_mega_pdf_url(row['key'], same_origin=True, week=row.get('week') or ''), quote=True)}\">Mega PDF</a>"
            f"<a class=\"live-btn secondary\" href=\"{html.escape(_ocr_standalone_url(row['key']), quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">Text</a>"
            "</div>"
            "</div>"
            "</article>"
        )

    live_cards_html = "".join(_live_card(row) for row in live_rows)

    other_rows_html = "".join(_coming_soon_item_html(row) for row in other_rows)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Parish Press — Irish Catholic Bulletins</title>
  {favicon_link_tags()}
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

    .intro {{ padding: 18px 16px 2px; text-align: center; }}
    .intro h1 {{ margin: 0 auto 6px; max-width: 40rem; font-size: clamp(1.25rem, 3vw, 1.7rem); color: #114b4b; }}
    .intro p {{ margin: 0 auto; max-width: 38rem; color: #45565f; font-size: 1rem; line-height: 1.45; }}

    .content {{ padding: 16px 16px 10px; }}
    .section-title {{ margin: 8px 0 12px; font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: #4b5563; }}
    .live-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .live-card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 14px; overflow: hidden; box-shadow: 0 6px 16px rgba(15, 47, 47, 0.06); }}
    .live-card-photo {{ height: 118px; background: #0f2f2f; }}
    .live-card-photo-empty {{ background: linear-gradient(135deg, #1a6b6b, #3fae9a); }}
    .live-card-body {{ padding: 10px 12px 12px; }}
    .live-card-eyebrow {{
      margin: 0 0 4px;
      display: flex;
      flex-direction: column;
      gap: 1px;
      font-size: 0.68rem;
      font-weight: 600;
      color: #4b5563;
      letter-spacing: 0.01em;
      line-height: 1.25;
      white-space: nowrap;
    }}
    .live-card h2 {{ margin: 0 0 2px; font-size: 1.02rem; color: #114b4b; white-space: nowrap; }}
    .live-card h2.is-long {{ font-size: 0.82rem; }}
    .live-card h2.is-very-long {{ font-size: 0.7rem; }}
    .live-card-updated {{ margin: 0 0 8px; color: #6b7686; font-size: 0.78rem; }}
    .live-card-actions {{ display: flex; flex-direction: column; gap: 6px; }}
    .live-btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 7px 10px; border-radius: 8px; font-weight: 700; font-size: 0.8rem; text-decoration: none; }}
    .live-btn.primary {{ background: #1a6b6b; color: #fff; }}
    .live-btn.secondary {{ background: #eef8f7; color: #1a6b6b; border: 1px solid #cfe8e6; }}
    .live-btn:hover {{ opacity: 0.92; text-decoration: none; }}
    @media (max-width: 900px) {{
      .live-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 520px) {{
      .live-grid {{ grid-template-columns: 1fr; }}
    }}
    .more-dioceses {{ margin-top: 28px; background: #fff; border: 1px solid #d6ecea; border-radius: 14px; padding: 16px 20px; }}
    .more-dioceses summary {{ cursor: pointer; font-weight: 700; color: #1a6b6b; list-style: none; }}
    .more-dioceses summary::-webkit-details-marker {{ display: none; }}
    .more-dioceses summary::before {{ content: "▸ "; }}
    .more-dioceses[open] summary::before {{ content: "▾ "; }}
    .more-dioceses-note {{ margin: 10px 0 12px; color: #6b7280; font-size: 0.88rem; }}
    .more-dioceses-grid {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 6px 16px; }}
    .more-dioceses-grid li {{ margin: 0; font-size: 0.92rem; white-space: nowrap; }}
    .more-dioceses-grid li.is-long {{ font-size: 0.82rem; }}
    .more-dioceses-grid li.is-very-long {{ font-size: 0.7rem; }}
    .more-dioceses-grid a {{ color: #375569; text-decoration: none; }}
    .more-dioceses-grid a:hover {{ text-decoration: underline; color: #1a6b6b; }}
    .footer {{ border-top: 1px solid #d6ecea; margin-top: 28px; padding: 16px 16px 28px; color: #16202a; font-size: 0.92rem; line-height: 1.6; }}
    .footer .photo-credit {{ margin: 0 0 6px; color: #222; font-size: 0.65rem; font-weight: 400; line-height: 1.3; }}
    .footer a {{ color: #14524f; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
    @media (max-width: 640px) {{
      .live-btn {{ flex: 1 1 auto; justify-content: center; }}
      .hero-nav {{ width: 32px; height: 32px; font-size: 1.2rem; }}
    }}
    {scroll_top_css()}
  </style>
</head>
<body>
  <div class=\"topbar\">
    <div class=\"topbar-inner\">
      <div class=\"brand\">Parish Press <span>· Irish Catholic Bulletins</span></div>
      <p class=\"topbar-tagline\">Weekly parish bulletins, free to read.</p>
    </div>
  </div>
  {_hero_slider_html()}
  <main class=\"content\">
    <div class=\"intro\">
      <h1>Welcome to Parish Press</h1>
      <p>Weekly Catholic parish bulletins from across Ireland, in one place. Parish Press is an ongoing project. Searchable text is produced automatically from each week's PDFs and may be incomplete — please confirm Mass times, names, and notices against the original PDF.</p>
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
    <p class=\"photo-credit\">{html.escape(_photo_credit_line())}</p>
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
  {scroll_top_js()}
  </script>
  {scroll_top_html()}
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
  {favicon_link_tags()}
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


def _mega_pdf_url(diocese_key: str, *, same_origin: bool = False, week: str = "") -> str:
    stem = diocese_key.replace("-", "_")
    filename = f"{stem}_mega_bulletin.pdf"
    # Same-origin path avoids the github.io → parishpress.ie 301, which
    # breaks or delays HTTP Range requests on phones (14–20 MB mega PDFs).
    if same_origin:
        url = f"/mega_pdf/{filename}"
    else:
        pages_base = "https://raphoe-diocese.github.io/parish_harvester"
        url = f"{pages_base}/mega_pdf/{filename}"
    # Phones cache this URL. Stamp the harvest Sunday so Open/Download
    # cannot keep last week's file (Frank 06/09/2026: Clogher still 23/08).
    return with_mega_pdf_week(url, week)


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


def _pdf_standalone_url(diocese_key: str, week: str = "") -> str:
    standalone = _latest_pdf_standalone(diocese_key)
    pages_base = "https://raphoe-diocese.github.io/parish_harvester"
    if standalone is not None:
        return f"{pages_base}/bulletins/{standalone.name}"
    return _mega_pdf_url(diocese_key, same_origin=True, week=week)


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

        week_summary = None
        if diocese.key in LIVE_DIOCESES and trained:
            parish_links = _parish_links_for_big_bulletin(diocese.key, report_path)
            ocr_text, ocr_is_html = _ocr_content_for_diocese(diocese.key)
            display_short = diocese.name.removesuffix(" Diocese").strip() or diocese.name
            if display_short == "Down and Connor":
                display_short = "Down & Connor"
            week_summary = build_diocese_week_summary(
                diocese.key,
                diocese_display_name=diocese.name,
                recipes_root=RECIPES_DIR,
                parish_status_path=REPO_ROOT / "parishes" / "parish_status.json",
            )
            intro_html = render_diocese_intro_html(week_summary)
            render_diocese_raphoe_page(
                parish_links=parish_links,
                out_path=out_path,
                mega_pdf_url=_mega_pdf_url(diocese.key, same_origin=True, week=target_date),
                ocr_standalone_url=_ocr_standalone_url(diocese.key),
                pdf_standalone_url=_pdf_standalone_url(diocese.key, week=target_date),
                ocr_text=ocr_text,
                ocr_is_html=ocr_is_html,
                week_label=week_label if target_date else "",
                diocese_display_name=diocese.name,
                headline=f"{display_short} Collated Bulletin",
                internal_parish_hrefs=_internal_parish_hrefs(diocese.key, docs_dir),
                intro_html=intro_html,
                parish_page_index=load_mega_page_index(docs_dir, diocese.key),
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
        status_label = _status_label(avg)
        ready_count, total_count = _card_counts_from_summary(week_summary)
        rows.append(
            {
                "key": diocese.key,
                "name": diocese.name,
                "dot": dot,
                "status_label": status_label,
                "updated": updated_label,
                "week": target_date or "",
                "ready_count": ready_count,
                "total_count": total_count,
            }
        )

    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(_landing_page(rows), encoding="utf-8")
    subscribe_dir = docs_dir / "subscribe"
    subscribe_dir.mkdir(parents=True, exist_ok=True)
    (subscribe_dir / "index.html").write_text(_subscribe_page(dioceses), encoding="utf-8")
