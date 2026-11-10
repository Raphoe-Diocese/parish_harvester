#!/usr/bin/env python3
"""Check the 29/10/2026 pasted parish websites for this Sunday. GitHub only.

A parish that is not already outcome ok for 08/11/2026, and not already in
parishes/pasted_sites_scan.json, is also probed with the brain's proved paths.
New hits go to parishes/pasted_brain_scan.json. Recipes are not edited.
"""
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

from harvester.bulletin_freshness import extract_bulletin_date  # noqa: E402
from harvester.recipe_brain import (  # noqa: E402
    _http_get,
    accepted_hunt_dates,
    candidate_probe_urls,
    prove_this_week_file,
)

_LINK_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)
_KEEP_RE = re.compile(r"newsletter|bulletin|\.pdf|uploads/2026/11", re.I)
_DIRECT_FILE = (".pdf", ".jpg", ".jpeg", ".png")

LIST_PATH = REPO / "parishes" / "cloud_sites_2026-10-29.json"
PRIOR_HITS_PATH = REPO / "parishes" / "pasted_sites_scan.json"
OUT_PATH = REPO / "parishes" / "pasted_brain_scan.json"
TARGET = date(2026, 11, 8)


def _facebook(url: str) -> bool:
    lowered = (url or "").lower()
    return "facebook.com" in lowered or "fb.watch" in lowered


def _wix_hash(url: str) -> bool:
    """A Wix file hash is not a stable bulletin address. Do not pin it."""
    lowered = (url or "").lower()
    if "/_files/ugd/" in lowered:
        return True
    if "wixstatic.com" not in lowered:
        return False
    return extract_bulletin_date(url) != TARGET


def _keep_probe(url: str) -> bool:
    """True when this URL can still be the 08/11/2026 file.

    09-11-08.pdf is 2009-11-08. 11.08.26.pdf is 2026-08-11.
    A name that already has a different date is not this Sunday.
    """
    url = (url or "").strip()
    if not url.startswith("http"):
        return False
    if _facebook(url) or _wix_hash(url):
        return False
    named = extract_bulletin_date(url)
    if named is not None and named != TARGET:
        return False
    return True


def _extra_urls(page_url: str) -> list[str]:
    """Newsletter links on the pasted page, plus the WordPress file list."""
    found: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        url = (url or "").strip()
        if not _keep_probe(url) or url in seen:
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


def brain_probe_urls(page_url: str) -> list[str]:
    """Brain paths for this start URL. Direct files first. No Facebook. No Wix hash.

    A filename dated on another day is left out. Only 08/11/2026 can count.
    """
    direct: list[str] = []
    later: list[str] = []
    seen: set[str] = set()

    def add(bucket: list[str], url: str) -> None:
        url = (url or "").strip()
        if not url or url in seen or not _keep_probe(url):
            return
        seen.add(url)
        bucket.append(url)

    for url, _site, _pattern in candidate_probe_urls(page_url):
        path = urlparse(url).path.lower()
        if path.endswith(_DIRECT_FILE):
            add(direct, url)
        else:
            add(later, url)
    return direct + later


def _prove_url(url: str, accepted: set[date]) -> dict | None:
    if not _keep_probe(url):
        return None
    proved = prove_this_week_file(url, accepted)
    if not proved or proved.get("date") != TARGET.isoformat():
        return None
    final = str(proved.get("url") or "")
    if not _keep_probe(final):
        return None
    return proved


def skip_reason(row: dict, parishes: dict, prior_hit_keys: set[str]) -> str | None:
    """Why this pasted row is not probed. None means probe it."""
    key = str(row.get("key") or "")
    url = str(row.get("url") or "")
    if not url.startswith("http"):
        return "no_website"
    if _facebook(url):
        return "facebook"
    current = parishes.get(key) or {}
    if current.get("outcome") == "ok" and current.get("bulletin_date") == TARGET.isoformat():
        return "saved"
    if key and key in prior_hit_keys:
        return "prior_hit"
    return None


def rows_to_probe(rows: list[dict], parishes: dict, prior_hit_keys: set[str]) -> list[dict]:
    return [row for row in rows if skip_reason(row, parishes, prior_hit_keys) is None]


def load_prior_hit_keys(path: Path | None = None) -> set[str]:
    file_path = path or PRIOR_HITS_PATH
    if not file_path.is_file():
        return set()
    try:
        report = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    keys: set[str] = set()
    for hit in report.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        key = str(hit.get("key") or "")
        if key:
            keys.add(key)
    return keys


def _one(row: dict, accepted: set[date]) -> dict:
    url = str(row.get("url") or "")
    key = str(row.get("key") or "")
    proved: dict | None = None
    try:
        tried: set[str] = set()

        def try_url(candidate: str) -> None:
            nonlocal proved
            candidate = (candidate or "").strip()
            if not candidate or candidate in tried or not _keep_probe(candidate):
                return
            tried.add(candidate)
            proved = _prove_url(candidate, accepted)

        for candidate in brain_probe_urls(url):
            try_url(candidate)
            if proved is not None:
                break
        if proved is None:
            try_url(url)
        if proved is None:
            for extra in _extra_urls(url):
                try_url(extra)
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
    prior_keys = load_prior_hit_keys()
    skipped = {"saved": 0, "prior_hit": 0, "facebook": 0, "no_website": 0}
    todo: list[dict] = []
    for row in rows:
        reason = skip_reason(row, parishes, prior_keys)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        todo.append(row)
    accepted = accepted_hunt_dates(TARGET)
    hits: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_one, row, accepted) for row in todo]
        for future in as_completed(futures):
            done += 1
            row = future.result()
            if row.get("found"):
                hits.append(row)
                print(f"FOUND {row['key']} {row.get('bulletin_url')}", flush=True)
            elif done % 25 == 0 or done == len(todo):
                print(f"progress {done}/{len(todo)} hits {len(hits)}", flush=True)
    hits.sort(key=lambda item: str(item.get("key") or ""))
    report = {
        "target": TARGET.isoformat(),
        "checked": len(todo),
        "skipped_saved": skipped.get("saved", 0),
        "skipped_prior_hits": skipped.get("prior_hit", 0),
        "found_this_sunday": len(hits),
        "hits": hits,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "checked",
                    "skipped_saved",
                    "skipped_prior_hits",
                    "found_this_sunday",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
