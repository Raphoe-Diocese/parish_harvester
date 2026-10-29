"""Bulk dig for webcam-host bulletins (MCN, churchmedia, churchservices).

Frank 29/10/2026: do not hand-click every parish. List cameras/channels,
reuse the same JSON/API helpers harvest already uses, emit a table of who
has a newsletter URL + stated date. Cloud agent can run ``--ireland``.
This laptop should stick to ``--county`` proves.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .utils import (
    churchmedia_channel_about_url,
    churchmedia_newsletter_url_from_about,
    churchmedia_slug_from_url,
    extract_mcn_church_id,
    mcn_newsletter_stated_date,
    mcn_newsletter_url_from_profile,
    mcn_profile_data_url,
)

# ROI + NI — MCN Cameras?County= accepts these names (proved Donegal/Dublin/…).
MCN_COUNTIES: tuple[str, ...] = (
    "Antrim",
    "Armagh",
    "Carlow",
    "Cavan",
    "Clare",
    "Cork",
    "Derry",
    "Donegal",
    "Down",
    "Dublin",
    "Fermanagh",
    "Galway",
    "Kerry",
    "Kildare",
    "Kilkenny",
    "Laois",
    "Leitrim",
    "Limerick",
    "Longford",
    "Louth",
    "Mayo",
    "Meath",
    "Monaghan",
    "Offaly",
    "Roscommon",
    "Sligo",
    "Tipperary",
    "Tyrone",
    "Waterford",
    "Westmeath",
    "Wexford",
    "Wicklow",
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_CAMERA_HREF_RE = re.compile(r"""href=["'](/Camera/[^"']+)["']""", re.I)
_CSTV_PLAYER_RE = re.compile(
    r"""href=["'](https?://(?:www\.)?churchservices\.tv/([a-z0-9][a-z0-9-]{1,80}))/?["']""",
    re.I,
)
_CSTV_RESERVED = frozenset(
    {
        "timetable",
        "feed",
        "comments",
        "wp-json",
        "wp-content",
        "wp-includes",
        "wp-admin",
        "xmlrpc.php",
        "category",
        "tag",
        "author",
        "page",
        "about",
        "contact",
        "privacy",
        "donate",
    }
)
_PDF_HREF_RE = re.compile(
    r"""href=["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
    re.I,
)
_BULLETIN_WORD_RE = re.compile(r"newsletter|bulletin|nuachtlitir|parish[\s-]?news", re.I)


@dataclass(frozen=True)
class DigHit:
    host: str
    source_url: str
    title: str
    newsletter_url: str | None
    stated_date: str | None
    note: str = ""


def _http_get(url: str, *, timeout_s: float = 25.0) -> str:
    request = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8", "ignore")


def _http_json(url: str, *, method: str = "GET", body: bytes | None = None) -> dict | None:
    headers = {
        "User-Agent": _UA,
        "Accept": "application/json",
    }
    if method.upper() == "POST":
        headers["Content-Type"] = "application/json;charset=UTF-8"
        data = body if body is not None else b"{}"
    else:
        data = None
    request = Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore") or "{}")
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def parse_mcn_camera_paths(html: str) -> list[str]:
    """Return unique ``/Camera/…`` paths from a county listing page."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _CAMERA_HREF_RE.finditer(html or ""):
        path = match.group(1).split("?")[0].rstrip("/")
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def list_mcn_cameras(county: str, *, sleep_s: float = 0.0) -> list[str]:
    """Absolute Camera URLs for one MCN county listing."""
    name = (county or "").strip()
    if not name:
        return []
    url = f"https://mcn.live/Cameras?County={name}"
    html = _http_get(url)
    if sleep_s > 0:
        time.sleep(sleep_s)
    paths = parse_mcn_camera_paths(html)
    return [f"https://mcn.live{path}" for path in paths]


def dig_mcn_camera(camera_url: str) -> DigHit:
    """Camera page → ProfileDataByJson → Latest Bulletin URL + card date."""
    raw = (camera_url or "").strip()
    title = raw.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    if not raw:
        return DigHit("mcn", "", "", None, None, "empty url")
    try:
        html = _http_get(raw)
    except Exception as exc:
        return DigHit("mcn", raw, title, None, None, f"camera page: {exc}")
    church_id = extract_mcn_church_id(html)
    if not church_id:
        return DigHit("mcn", raw, title, None, None, "no hfChurchId")
    api = mcn_profile_data_url(raw, church_id)
    payload = _http_json(api, method="POST")
    if not payload:
        return DigHit("mcn", raw, title, None, None, "profile json failed")
    newsletter = mcn_newsletter_url_from_profile(payload)
    stated = mcn_newsletter_stated_date(payload)
    name = ""
    church = payload.get("church") if isinstance(payload.get("church"), dict) else {}
    if isinstance(church, dict):
        name = str(church.get("name") or church.get("churchName") or "").strip()
    if name:
        title = name
    note = "ok" if newsletter else "no newsletter on profile"
    return DigHit(
        host="mcn",
        source_url=raw,
        title=title,
        newsletter_url=newsletter,
        stated_date=stated.isoformat() if isinstance(stated, date) else None,
        note=note,
    )


def parse_churchservices_player_urls(html: str) -> list[str]:
    """Unique churchservices.tv player page URLs from a directory/timetable HTML."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _CSTV_PLAYER_RE.finditer(html or ""):
        full = match.group(1).rstrip("/")
        slug = match.group(2).lower()
        if slug in _CSTV_RESERVED or slug.startswith("wp-"):
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def list_churchservices_players(*, sleep_s: float = 0.0) -> list[str]:
    """Player URLs from the public churchservices.tv timetable page."""
    html = _http_get("https://www.churchservices.tv/timetable")
    if sleep_s > 0:
        time.sleep(sleep_s)
    return parse_churchservices_player_urls(html)


def dig_churchservices_page(player_url: str) -> DigHit:
    """Pointer host: only report a real newsletter PDF href when present."""
    raw = (player_url or "").strip()
    title = raw.rstrip("/").rsplit("/", 1)[-1]
    if not raw:
        return DigHit("churchservices", "", "", None, None, "empty url")
    try:
        html = _http_get(raw)
    except Exception as exc:
        return DigHit("churchservices", raw, title, None, None, f"page: {exc}")
    best: str | None = None
    for match in _PDF_HREF_RE.finditer(html):
        href = match.group(1).strip()
        abs_url = urljoin(raw, href)
        if _BULLETIN_WORD_RE.search(abs_url) or _BULLETIN_WORD_RE.search(href):
            best = abs_url
            break
        if best is None:
            best = abs_url
    if best and _BULLETIN_WORD_RE.search(best):
        return DigHit(
            "churchservices",
            raw,
            title,
            best,
            None,
            "pdf on page (pointer host — prove date before recipe)",
        )
    return DigHit(
        "churchservices",
        raw,
        title,
        None,
        None,
        "webcam only — no bulletin PDF on page",
    )


def dig_churchmedia_slug(slug: str) -> DigHit:
    """getChannelAbout → current newsletter PDF (token changes each week)."""
    token = (slug or "").strip()
    source = f"https://churchmedia.tv/{token}" if token else ""
    if not token:
        return DigHit("churchmedia", "", "", None, None, "empty slug")
    if churchmedia_slug_from_url(source) != token:
        return DigHit("churchmedia", source, token, None, None, "bad slug")
    api = churchmedia_channel_about_url(token)
    payload = _http_json(api, method="GET")
    if not payload:
        return DigHit("churchmedia", source, token, None, None, "about api failed")
    newsletter = churchmedia_newsletter_url_from_about(payload)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    name = ""
    if isinstance(data, dict):
        name = str(data.get("name") or data.get("title") or token).strip()
    return DigHit(
        host="churchmedia",
        source_url=source,
        title=name or token,
        newsletter_url=newsletter,
        stated_date=None,
        note="ok" if newsletter else "no newsletter_url",
    )


def churchmedia_slugs_from_recipes(recipes_root: Path) -> list[str]:
    """Collect churchmedia.tv slugs already stored in recipes (seed list)."""
    root = Path(recipes_root)
    seen: set[str] = set()
    out: list[str] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key in ("start_url", "example_url"):
            slug = churchmedia_slug_from_url(str(data.get(key) or ""))
            if slug and slug not in seen:
                seen.add(slug)
                out.append(slug)
        explicit = str(data.get("churchmedia_slug") or "").strip()
        if explicit and explicit not in seen:
            seen.add(explicit)
            out.append(explicit)
    return out


def dig_mcn_county(
    county: str,
    *,
    sleep_s: float = 0.35,
    limit: int | None = None,
) -> list[DigHit]:
    cameras = list_mcn_cameras(county, sleep_s=sleep_s)
    if limit is not None:
        cameras = cameras[: max(0, int(limit))]
    hits: list[DigHit] = []
    for camera in cameras:
        hits.append(dig_mcn_camera(camera))
        if sleep_s > 0:
            time.sleep(sleep_s)
    return hits


def dig_ireland_mcn(
    *,
    sleep_s: float = 0.35,
    counties: tuple[str, ...] | None = None,
    limit_per_county: int | None = None,
) -> list[DigHit]:
    """Walk every MCN county. Prefer Cursor cloud — not the 16GB laptop."""
    hits: list[DigHit] = []
    for county in counties or MCN_COUNTIES:
        hits.extend(
            dig_mcn_county(county, sleep_s=sleep_s, limit=limit_per_county)
        )
    return hits


def write_hits(path: Path, hits: list[DigHit]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(hit) for hit in hits]
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_summary(hits: list[DigHit]) -> None:
    with_file = [h for h in hits if h.newsletter_url]
    print(f"dig rows={len(hits)} with_newsletter={len(with_file)}")
    for hit in with_file[:40]:
        print(
            f"  [{hit.host}] {hit.title} | {hit.stated_date or '-'} | {hit.newsletter_url}"
        )
    if len(with_file) > 40:
        print(f"  … {len(with_file) - 40} more with newsletter")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bulk dig MCN / churchmedia / churchservices for newsletter URLs. "
            "Use --county on this PC; --ireland belongs in Cursor cloud."
        )
    )
    parser.add_argument(
        "--hosts",
        default="mcn",
        help="Comma list: mcn,churchmedia,churchservices (default mcn)",
    )
    parser.add_argument("--county", default="", help="One MCN county (e.g. Donegal)")
    parser.add_argument(
        "--ireland",
        action="store_true",
        help="All MCN counties (cloud). Do not run full Ireland on the laptop.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max cameras/slugs per source")
    parser.add_argument("--sleep", type=float, default=0.35, help="Pause between requests")
    parser.add_argument(
        "--out",
        default="",
        help="Write JSON rows (e.g. Bulletins/webcam_bulletin_dig.json)",
    )
    parser.add_argument(
        "--recipes-root",
        default="parishes/recipes",
        help="Recipe tree for churchmedia slug seeds",
    )
    parser.add_argument(
        "--churchmedia-slugs",
        default="",
        help="Extra comma-separated churchmedia slugs",
    )
    args = parser.parse_args(argv)

    hosts = {h.strip().lower() for h in str(args.hosts).split(",") if h.strip()}
    limit = int(args.limit) if args.limit and args.limit > 0 else None
    sleep_s = max(0.0, float(args.sleep))
    hits: list[DigHit] = []

    if "mcn" in hosts:
        if args.ireland:
            print("WARNING: --ireland MCN crawl — prefer Cursor cloud, not this laptop.")
            hits.extend(
                dig_ireland_mcn(sleep_s=sleep_s, limit_per_county=limit)
            )
        elif args.county.strip():
            hits.extend(
                dig_mcn_county(args.county.strip(), sleep_s=sleep_s, limit=limit)
            )
        else:
            print("mcn: pass --county Donegal or --ireland")

    if "churchmedia" in hosts:
        slugs = churchmedia_slugs_from_recipes(Path(args.recipes_root))
        for extra in str(args.churchmedia_slugs).split(","):
            token = extra.strip()
            if token and token not in slugs:
                slugs.append(token)
        if limit is not None:
            slugs = slugs[:limit]
        for slug in slugs:
            hits.append(dig_churchmedia_slug(slug))
            if sleep_s > 0:
                time.sleep(sleep_s)

    if "churchservices" in hosts:
        players = list_churchservices_players(sleep_s=sleep_s)
        if limit is not None:
            players = players[:limit]
        for player in players:
            hits.append(dig_churchservices_page(player))
            if sleep_s > 0:
                time.sleep(sleep_s)

    _print_summary(hits)
    if args.out.strip():
        write_hits(Path(args.out.strip()), hits)
        print(f"wrote {args.out.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
