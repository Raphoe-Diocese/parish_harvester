#!/usr/bin/env python3
"""Check the 29/10/2026 pasted parish websites for this Sunday. GitHub only."""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.recipe_brain import (  # noqa: E402
    _http_get,
    accepted_hunt_dates,
    prove_this_week_file,
)

_LINK_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)
_KEEP_RE = re.compile(r"newsletter|bulletin|\.pdf|uploads/2026/11", re.I)

LIST_PATH = REPO / "parishes" / "cloud_sites_2026-10-29.json"
TARGET = date(2026, 11, 8)


def _extra_urls(page_url: str) -> list[str]:
    """Newsletter links on the pasted page, plus the WordPress file list."""
    found: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        url = (url or "").strip()
        if not url.startswith("http") or url in seen:
            return
        if "facebook.com" in url.lower():
            return
        seen.add(url)
        found.append(url)

    try:
        status, ctype, body, final = _http_get(page_url, max_bytes=180_000)
    except Exception:
        status, ctype, body, final = 0, "", b"", page_url
    if status == 200 and "html" in (ctype or "").lower():
        html = body.decode("utf-8", errors="ignore")
        for href in _LINK_RE.findall(html):
            if not _KEEP_RE.search(href):
                continue
            add(urljoin(final or page_url, href))
            if len(found) >= 8:
                break
    parsed = urlparse(page_url)
    if parsed.scheme and parsed.netloc and len(found) < 9:
        add(
            f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/media"
            "?per_page=20&search=newsletter"
        )
    return found


def _prove_url(url: str, accepted: set[date]) -> dict | None:
    proved = prove_this_week_file(url, accepted)
    if not proved or proved.get("date") != TARGET.isoformat():
        return None
    return proved


def _one(row: dict, accepted: set[date]) -> dict:
    url = str(row.get("url") or "")
    key = str(row.get("key") or "")
    try:
        proved = _prove_url(url, accepted)
        if proved is None:
            for extra in _extra_urls(url):
                proved = _prove_url(extra, accepted)
                if proved is not None:
                    break
    except Exception as exc:
        return {"key": key, "url": url, "error": str(exc)[:160]}
    if proved is None:
        return {"key": key, "url": url, "found": False}
    return {
        "key": key,
        "url": url,
        "found": True,
        "bulletin_url": proved.get("url"),
        "date": proved.get("date"),
        "kind": proved.get("kind"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    status = json.loads((REPO / "parishes" / "parish_status.json").read_text(encoding="utf-8"))
    parishes = status.get("parishes") or {}
    todo = []
    for row in rows:
        key = str(row.get("key") or "")
        current = parishes.get(key) or {}
        if current.get("outcome") == "ok" and current.get("bulletin_date") == TARGET.isoformat():
            continue
        if not str(row.get("url") or "").startswith("http"):
            continue
        todo.append(row)
    accepted = accepted_hunt_dates(TARGET)
    hits = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_one, row, accepted) for row in todo]
        for future in as_completed(futures):
            row = future.result()
            if row.get("found"):
                hits.append(row)
                print(f"FOUND {row['key']} {row.get('bulletin_url')}")
    report = {
        "target": TARGET.isoformat(),
        "checked": len(todo),
        "already_saved": len(rows) - len(todo),
        "found_this_sunday": len(hits),
        "hits": hits,
    }
    out = REPO / "parishes" / "pasted_sites_scan.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("checked", "already_saved", "found_this_sunday")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
