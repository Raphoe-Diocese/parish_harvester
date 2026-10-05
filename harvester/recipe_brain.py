"""Recipe Brain — remember which hub trick won, reuse it on the next parish.

24/7 skip-parish hub scan runs on GitHub Actions
(`.github/workflows/recipe-brain-hunt.yml`), not on Frank's laptop.
hint_for_url() is click-memory: one proved host must suggest the same
recipe shape for the next similar URL. remember_win() writes the trick
back into parishes/site_patterns.json.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from harvester.config import BASE_DIR, target_sunday
from harvester.utils import extract_date_from_string, format_uk_date

PATTERNS_PATH = BASE_DIR / "parishes" / "site_patterns.json"
RECIPES_DIR = BASE_DIR / "parishes" / "recipes"
CURSOR_PATH = BASE_DIR / "parishes" / "recipe_brain_cursor.json"
UA = "ParishPress-RecipeBrain/1.0 (+https://www.parishpress.ie/)"

_SKIP_HOSTS = {
    "facebook.com",
    "m.facebook.com",
    "www.facebook.com",
    "fb.watch",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
}
_DIRECTORY_HOSTS = {
    "dublindiocese.ie",
    "www.dublindiocese.ie",
    "vocations.ie",
    "www.vocations.ie",
    "catholicbishops.ie",
    "www.catholicbishops.ie",
}

_HREF_PDF_RE = re.compile(
    r"""href=["']([^"']+\.pdf[^"']*)["']""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HubHint:
    """A remembered trick for a bulletin host."""

    key: str
    site_type: str
    label: str
    confidence: str
    notes: tuple[str, ...]
    do_not: tuple[str, ...]
    pattern_key: str = ""


def _host(url: str) -> str:
    host = urlparse((url or "").strip()).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def hint_for_url(url: str) -> HubHint | None:
    """Return the remembered hub trick for *url*, or None."""
    raw = (url or "").strip()
    if not raw:
        return None
    host = _host(raw)
    path = urlparse(raw).path.lower()

    if host in {"mcn.live", "www.mcn.live"} or "mcn.live" in host:
        return HubHint(
            key="mcn_live",
            site_type="mcn_live_parish_page",
            label="MCN camera page newsletter (JSON, not the webcam)",
            confidence="high",
            notes=(
                "Newsletter sits on the MCN camera page. Harvest uses the profile JSON, not the stream.",
                "Start at the /Camera/ URL Frank trained. Do not pin a dated PDF.",
            ),
            do_not=(
                "Do not harvest the webcam video.",
                "Do not pin a dated newsletter filename.",
            ),
            pattern_key="mcn_live+direct_download",
        )

    if host == "churchmedia.tv":
        return HubHint(
            key="churchmedia",
            site_type="churchmedia_newsletter",
            label="churchmedia.tv latest newsletter button",
            confidence="high",
            notes=(
                "Use getChannelAbout for this week's PDF. Portaferry proved this.",
                "The public /newsletter/<token> path dies on the next upload.",
            ),
            do_not=("Do not pin churchmedia /newsletter/<token>.….pdf.",),
            pattern_key="churchmedia+direct_download",
        )

    if host == "mayo.ie" or path.startswith("/getmedia/"):
        return HubHint(
            key="mayo_ie",
            site_type="http_scrape_newest_pdf",
            label="Mayo County Council parish-newsletters listing",
            confidence="high",
            notes=(
                "Belmullet proved GET 200 on mayo.ie parish-newsletters. Date is in the link text and filename.",
                "Scrape the listing each week. The getmedia GUID changes.",
            ),
            do_not=(
                "Do not pin the getmedia GUID.",
                "Do not treat a PNG as a PDF recipe.",
            ),
            pattern_key="mayo_ie+direct_download",
        )

    if host in {"churchservices.tv", "www.churchservices.tv"}:
        return HubHint(
            key="churchservices_tv",
            site_type="link_only",
            label="churchservices.tv webcam — pointer only until a newsletter file is proved",
            confidence="low",
            notes=(
                "Webcam first. Look on the same page for a newsletter link. Else keep the real parish site.",
            ),
            do_not=(
                "Do not harvest the livestream as a bulletin.",
                "Do not invent a PDF because a webcam exists.",
            ),
            pattern_key="churchservices_tv+pointer",
        )

    if path.rstrip("/").endswith("current-newsletter"):
        return HubHint(
            key="current_newsletter_redirect",
            site_type="permanent_redirect_document",
            label="Permanent /current-newsletter/ path (Kildare / Naas pattern)",
            confidence="high",
            notes=(
                "Same URL every week. It redirects to this Sunday's PDF. Do not pin the dated upload.",
            ),
            do_not=("Do not pin the dated wp-content filename.",),
            pattern_key="current-newsletter+direct_download",
        )

    if "wp-json" in path or path.rstrip("/").endswith("newsletters"):
        return HubHint(
            key="wp_json_media",
            site_type="wp_json_newest_media",
            label="WordPress media library (Ashbourne / Askea pattern)",
            confidence="high",
            notes=(
                "Ashbourne: listing had no calendar date in the PDF href. wp-json scored the file.",
                "Askea: /newsletters/ lists dated PDFs. Do not pin the dated name.",
            ),
            do_not=("Do not pin a dated filename.", "Do not harvest Facebook."),
            pattern_key="wp_json+direct_download",
        )

    return None


def accepted_hunt_dates(today: date | None = None) -> set[date]:
    """This Sunday, last Sunday, and Fri–Mon around this Sunday."""
    sunday = target_sunday(today)
    prev = sunday - timedelta(days=7)
    days = {sunday, prev}
    for offset in (-2, -1, 0, 1):
        days.add(sunday + timedelta(days=offset))
    return days


def _blocked_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        bare = host[4:]
    else:
        bare = host
    return host in _SKIP_HOSTS or bare in _SKIP_HOSTS or host in _DIRECTORY_HOSTS or bare in _DIRECTORY_HOSTS


def load_skip_recipes(recipes_dir: Path | None = None) -> list[dict[str, Any]]:
    root = recipes_dir or RECIPES_DIR
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("skip") is not True:
            continue
        if data.get("alias_of"):
            continue
        data["_path"] = str(path)
        rows.append(data)
    return rows


def candidate_probe_urls(start_url: str) -> list[tuple[str, str, str]]:
    """Return (url, site_type, pattern_key) probes from remembered tricks.

    Does not invent Facebook or diocese-directory files.
    """
    raw = (start_url or "").strip()
    if not raw or _blocked_host(raw):
        return []
    parsed = urlparse(raw)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    hint = hint_for_url(raw)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(url: str, site_type: str, pattern_key: str) -> None:
        url = url.strip()
        if not url or url in seen or _blocked_host(url):
            return
        seen.add(url)
        out.append((url, site_type, pattern_key))

    if hint and hint.confidence == "high":
        add(raw, hint.site_type, hint.pattern_key or hint.key)

    if hint is None or hint.key != "churchservices_tv":
        add(
            origin.rstrip("/") + "/current-newsletter/",
            "permanent_redirect_document",
            "current-newsletter+direct_download",
        )
        add(
            origin.rstrip("/") + "/newsletters/",
            "http_scrape_newest_pdf",
            "wp_json+direct_download",
        )
        add(
            origin.rstrip("/") + "/wp-json/wp/v2/media?per_page=20",
            "wp_json_newest_media",
            "wp_json+direct_download",
        )
    return out


def _http_get(url: str, timeout: int = 20) -> tuple[int, str, bytes, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read(256_000)
        ctype = resp.headers.get("Content-Type") or ""
        final = resp.geturl() or url
        return int(resp.status), ctype, body, final


def _magic_ok(body: bytes, ctype: str) -> str | None:
    lowered = (ctype or "").lower()
    if body.startswith(b"%PDF") or "application/pdf" in lowered:
        return "pdf"
    if body[:3] == b"\xff\xd8\xff" or "image/jpeg" in lowered or "image/jpg" in lowered:
        return "jpeg"
    return None


def _date_ok(text: str, accepted: set[date]) -> date | None:
    found = extract_date_from_string(text)
    if found in accepted:
        return found
    return None


def prove_this_week_file(url: str, accepted: set[date]) -> dict[str, Any] | None:
    """GET 200 + %PDF/JPEG + date on the URL. No invented dates."""
    try:
        status, ctype, body, final = _http_get(url)
    except Exception:
        return None
    if status != 200:
        return None
    kind = _magic_ok(body, ctype)
    if kind == "pdf" and body.startswith(b"%PDF") is False and "json" in ctype.lower():
        return _prove_from_wp_json(body, url, accepted)
    if kind == "pdf" or (kind is None and "html" in ctype.lower()):
        if kind == "pdf":
            found = _date_ok(final, accepted) or _date_ok(url, accepted)
            if found is None:
                return None
            return {
                "url": final,
                "kind": "pdf",
                "bytes": len(body),
                "date": found.isoformat(),
            }
        return _prove_from_listing_html(body, final, accepted)
    if kind == "jpeg":
        found = _date_ok(final, accepted) or _date_ok(url, accepted)
        if found is None:
            return None
        return {
            "url": final,
            "kind": "jpeg",
            "bytes": len(body),
            "date": found.isoformat(),
        }
    if "json" in ctype.lower() or urlparse(url).path.lower().find("wp-json") >= 0:
        return _prove_from_wp_json(body, url, accepted)
    return None


def _prove_from_listing_html(body: bytes, page_url: str, accepted: set[date]) -> dict[str, Any] | None:
    try:
        html = body.decode("utf-8", errors="ignore")
    except Exception:
        return None
    for href in _HREF_PDF_RE.findall(html):
        absolute = urljoin(page_url, href)
        found = _date_ok(absolute, accepted) or _date_ok(href, accepted)
        if found is None:
            continue
        try:
            status, ctype, blob, final = _http_get(absolute)
        except Exception:
            continue
        if status != 200 or _magic_ok(blob, ctype) != "pdf":
            continue
        if not blob.startswith(b"%PDF"):
            continue
        return {
            "url": final,
            "kind": "pdf",
            "bytes": len(blob),
            "date": found.isoformat(),
        }
    return None


def _prove_from_wp_json(body: bytes, page_url: str, accepted: set[date]) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    items = payload if isinstance(payload, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_url") or "")
        mime = str((item.get("mime_type") or "")).lower()
        if not source.lower().endswith(".pdf") and "pdf" not in mime:
            continue
        found = _date_ok(source, accepted)
        if found is None:
            continue
        try:
            status, ctype, blob, final = _http_get(source)
        except Exception:
            continue
        if status != 200 or not blob.startswith(b"%PDF"):
            continue
        return {
            "url": final,
            "kind": "pdf",
            "bytes": len(blob),
            "date": found.isoformat(),
        }
    return None


def remember_win(
    pattern_key: str,
    parish_key: str,
    note: str,
    patterns_path: Path | None = None,
) -> None:
    """Write a proved trick into site_patterns.json (click memory)."""
    path = patterns_path or PATTERNS_PATH
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "description": "Learned site layout patterns.", "patterns": {}}
    patterns = data.setdefault("patterns", {})
    row = patterns.get(pattern_key)
    if not isinstance(row, dict):
        row = {
            "page_type": pattern_key.split("+")[0],
            "recipe_flow": "direct_download",
            "label": pattern_key,
            "advice": note,
            "operator_notes": [],
            "do_not": ["Do not pin a dated filename.", "Do not harvest Facebook."],
            "example_parishes": [],
            "success_count": 0,
        }
        patterns[pattern_key] = row
    examples = row.setdefault("example_parishes", [])
    if parish_key and parish_key not in examples:
        examples.append(parish_key)
    row["success_count"] = int(row.get("success_count") or 0) + 1
    notes = row.setdefault("operator_notes", [])
    if note and note not in notes:
        notes.append(note)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unskip_recipe(recipe: dict[str, Any], *, site_type: str, start_url: str, note: str) -> None:
    path = Path(recipe["_path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["skip"] = False
    data.pop("reason", None)
    if data.get("status") == "inactive":
        data["status"] = "active"
    data["site_type"] = site_type
    data["playbook_type"] = "direct_download"
    data["start_url"] = start_url
    data["recorded_date"] = date.today().isoformat()
    data["steps"] = [{"action": "goto", "url": start_url}]
    if site_type == "permanent_redirect_document":
        data["steps"] = [{"action": "download", "url": start_url, "use_target_url": True}]
    notes = data.setdefault("operator_notes", [])
    notes.append(note)
    do_not = data.setdefault("do_not", [])
    for line in ("Do not pin a dated filename.", "Do not harvest Facebook."):
        if line not in do_not:
            do_not.append(line)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def scan_skipped(
    *,
    recipes_dir: Path | None = None,
    patterns_path: Path | None = None,
    cursor_path: Path | None = None,
    limit: int = 25,
    apply: bool = False,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Probe skipped recipes with remembered hub tricks. Optionally unskip."""
    skips = load_skip_recipes(recipes_dir)
    cursor_file = cursor_path or CURSOR_PATH
    offset = 0
    if cursor_file.exists():
        try:
            offset = int(json.loads(cursor_file.read_text(encoding="utf-8")).get("offset") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            offset = 0
    if skips:
        offset = offset % len(skips)
    window = skips[offset : offset + limit]
    if len(window) < limit:
        window.extend(skips[: max(0, limit - len(window))])
    accepted = accepted_hunt_dates(today)
    wins: list[dict[str, Any]] = []
    for recipe in window:
        start = str(recipe.get("start_url") or "")
        key = str(recipe.get("parish_key") or Path(recipe["_path"]).stem)
        for url, site_type, pattern_key in candidate_probe_urls(start):
            proved = prove_this_week_file(url, accepted)
            if not proved:
                continue
            listing_url = url
            if site_type == "permanent_redirect_document" and "/current-newsletter" in urlparse(url).path.lower():
                listing_url = url
            elif site_type == "wp_json_newest_media":
                listing_url = start or url
            elif site_type == "http_scrape_newest_pdf":
                listing_url = url
            uk = format_uk_date(proved["date"])
            note = (
                f"{format_uk_date(date.today())} Recipe Brain hub scan: proved GET 200 "
                f"{proved['kind']} {proved.get('bytes')} bytes dated {uk}. "
                f"Do not pin {proved['url']}."
            )
            win = {
                "parish_key": key,
                "site_type": site_type,
                "pattern_key": pattern_key,
                "start_url": listing_url,
                "proved_url": proved["url"],
                "date": proved["date"],
            }
            wins.append(win)
            if apply:
                _unskip_recipe(
                    recipe,
                    site_type=site_type,
                    start_url=listing_url
                    if site_type != "wp_json_newest_media"
                    else (start or listing_url),
                    note=note,
                )
                remember_win(pattern_key, key, note, patterns_path=patterns_path)
            break
    next_offset = offset + limit
    cursor_file.write_text(json.dumps({"offset": next_offset}, indent=2) + "\n", encoding="utf-8")
    return wins
