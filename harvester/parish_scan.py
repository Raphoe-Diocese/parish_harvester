"""Scan parish websites for this Sunday's bulletin.

Fast pass: the page that worked before, then the first brain addresses.
Deep pass: the rest of the proved tricks (listing, WordPress media,
current-newsletter, Sunday file names), only where the fast pass found nothing.

Runs on GitHub. A proved PDF or JPEG is written into site_patterns. A
skipped recipe is turned back on. Facebook, no website, and blocked hosts
are left out. Stale and missed-week parishes are included every run.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harvester.recipe_brain import (
    RECIPES_DIR,
    _blocked_host,
    _unskip_recipe,
    accepted_hunt_dates,
    candidate_probe_urls,
    prove_this_week_file,
    remember_win,
)
from harvester.utils import format_uk_date

REPORT_NAME = "parish_scan_report.json"


def load_scan_recipes(recipes_dir: Path | None = None) -> list[dict[str, Any]]:
    root = recipes_dir or RECIPES_DIR
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = str(path)
        rows.append(data)
    return rows


def leave_reason(recipe: dict[str, Any]) -> str | None:
    """Why this parish is not scanned. None means scan it."""
    if recipe.get("alias_of"):
        return "alias"
    url = str(recipe.get("start_url") or "").strip()
    reason = " ".join(
        str(recipe.get(key) or "") for key in ("reason", "dead_reason")
    ).lower()
    lowered = url.lower()
    if (
        "facebook.com" in lowered
        or "facebook-only" in reason
        or "cannot scrape facebook" in reason
    ):
        return "facebook"
    if "no parish website" in reason or not lowered.startswith("http"):
        return "no_website"
    if not url or _blocked_host(url):
        return "blocked"
    return None


def ordered_probes(recipe: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Past success first, then the brain's proved address list.

    The saved page is what worked last time, including a stale recipe.
    /newsletter/ and /bulletin/ are the two listing paths with the most wins.
    A dated file name is not probed. That name dies next week.
    """
    start = str(recipe.get("start_url") or "").strip()
    site_type = str(recipe.get("site_type") or "http_scrape_newest_pdf")
    saved_key = f"saved_{site_type}"
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(url: str, site: str, pattern: str) -> None:
        url = (url or "").strip()
        if not url or url in seen or _blocked_host(url):
            return
        if "facebook.com" in url.lower():
            return
        seen.add(url)
        out.append((url, site, pattern))

    add(start, site_type, saved_key)
    example = str(recipe.get("example_url") or "").strip()
    example_path = example.lower().split("?", 1)[0]
    if example.startswith("http") and not example_path.endswith(
        (".pdf", ".jpg", ".jpeg", ".png", ".docx")
    ):
        add(example, site_type, saved_key)
    parsed = urlparse(start)
    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        add(origin + "/newsletter/", "http_scrape_newest_pdf", "pdf_link_list+click_then_pdf")
        add(origin + "/bulletin/", "http_scrape_newest_pdf", "pdf_link_list+click_then_pdf")
    for url, site, pattern in candidate_probe_urls(start):
        add(url, site, pattern)
    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        for path in (
            "/publications/",
            "/bulletins/",
            "/parish-newsletter/",
            "/parish-bulletin/",
            "/weekly-newsletter/",
            "/news/",
        ):
            add(origin + path, "http_scrape_newest_pdf", "pdf_link_list+click_then_pdf")
    return out[:14]


def _phase_urls(recipe: dict[str, Any], *, phase: str, mode: str) -> list[tuple[str, str, str]]:
    urls = ordered_probes(recipe)
    if mode == "more":
        return urls[8:14]
    if phase == "fast":
        return urls[:3]
    if mode == "both":
        return urls[3:8]
    return urls[:8]


def _probe_one(
    recipe: dict[str, Any],
    urls: list[tuple[str, str, str]],
    accepted: set[date],
) -> dict[str, Any]:
    key = str(recipe.get("parish_key") or Path(str(recipe.get("_path") or "")).stem)
    try:
        for url, site_type, pattern_key in urls:
            proved = prove_this_week_file(url, accepted)
            if not proved or proved.get("kind") not in {"pdf", "jpeg"}:
                continue
            return {
                "parish_key": key,
                "found": True,
                "proved": proved,
                "site_type": site_type,
                "pattern_key": pattern_key or "homepage_listing",
                "tried": url,
            }
    except Exception as exc:
        return {"parish_key": key, "found": False, "error": str(exc)[:160]}
    return {"parish_key": key, "found": False}


def _listing_url(recipe: dict[str, Any], hit: dict[str, Any]) -> str:
    start = str(recipe.get("start_url") or "")
    site_type = str(hit.get("site_type") or "")
    tried = str(hit.get("tried") or start)
    if site_type == "wp_json_newest_media":
        return start or tried
    return tried or start


def _teach(
    recipe: dict[str, Any],
    hit: dict[str, Any],
    *,
    patterns_path: Path | None,
) -> None:
    key = str(hit["parish_key"])
    proved = hit["proved"]
    when = format_uk_date(date.today())
    bulletin = format_uk_date(date.fromisoformat(str(proved["date"])))
    note = (
        f"{when} Parish scan: proved {proved.get('kind')} dated {bulletin}. "
        f"Do not pin {proved.get('url')}."
    )
    remember_win(
        str(hit.get("pattern_key") or "homepage_listing"),
        key,
        note,
        patterns_path=patterns_path,
    )
    skipped = recipe.get("skip") is True or str(recipe.get("status") or "").lower() == "inactive"
    if not skipped:
        return
    _unskip_recipe(
        recipe,
        site_type=str(hit.get("site_type") or "http_scrape_newest_pdf"),
        start_url=_listing_url(recipe, hit),
        note=note,
    )


def _run_phase(
    recipes: list[dict[str, Any]],
    *,
    urls_for,
    accepted: set[date],
    workers: int,
) -> list[dict[str, Any]]:
    if not recipes:
        return []
    found: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [
            pool.submit(_probe_one, recipe, urls_for(recipe), accepted)
            for recipe in recipes
        ]
        for future in as_completed(futures):
            row = future.result()
            if row.get("found"):
                found.append(row)
    return found


def run_parish_scan(
    *,
    mode: str = "both",
    workers: int = 30,
    apply: bool = False,
    recipes_dir: Path | None = None,
    patterns_path: Path | None = None,
    report_path: Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Scan websites. Teach the brain only when apply is true and a file is proved."""
    mode = mode if mode in {"fast", "deep", "both", "more"} else "both"
    recipes = load_scan_recipes(recipes_dir)
    left: dict[str, int] = {}
    pool: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for recipe in recipes:
        reason = leave_reason(recipe)
        if reason:
            left[reason] = left.get(reason, 0) + 1
            continue
        key = str(recipe.get("parish_key") or Path(recipe["_path"]).stem)
        pool.append(recipe)
        by_key[key] = recipe
    accepted = accepted_hunt_dates(today)

    def fast_urls(recipe: dict[str, Any]) -> list[tuple[str, str, str]]:
        return _phase_urls(recipe, phase="fast", mode=mode)

    def deep_urls(recipe: dict[str, Any]) -> list[tuple[str, str, str]]:
        return _phase_urls(recipe, phase="deep", mode=mode)

    hits: list[dict[str, Any]] = []
    if mode == "more":
        hits.extend(_run_phase(pool, urls_for=deep_urls, accepted=accepted, workers=workers))
    elif mode in {"fast", "both"}:
        hits.extend(_run_phase(pool, urls_for=fast_urls, accepted=accepted, workers=workers))
    found_keys = {str(hit["parish_key"]) for hit in hits}
    if mode in {"deep", "both"}:
        remaining = [recipe for recipe in pool if str(recipe.get("parish_key") or Path(recipe["_path"]).stem) not in found_keys]
        hits.extend(_run_phase(remaining, urls_for=deep_urls, accepted=accepted, workers=workers))

    taught = 0
    if apply:
        for hit in hits:
            recipe = by_key.get(str(hit["parish_key"]))
            if recipe is None:
                continue
            _teach(recipe, hit, patterns_path=patterns_path)
            taught += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": mode,
        "workers": workers,
        "scanned": len(pool),
        "wins": len(hits),
        "taught": taught,
        "missed": len(pool) - len({str(hit["parish_key"]) for hit in hits}),
        "left_out": left,
        "hits": [
            {
                "parish_key": hit["parish_key"],
                "date": (hit.get("proved") or {}).get("date"),
                "url": (hit.get("proved") or {}).get("url"),
                "pattern_key": hit.get("pattern_key"),
            }
            for hit in hits
        ],
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
