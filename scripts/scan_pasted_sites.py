#!/usr/bin/env python3
"""Check the 29/10/2026 pasted parish websites for this Sunday. GitHub only."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.recipe_brain import (  # noqa: E402
    accepted_hunt_dates,
    prove_this_week_file,
)

LIST_PATH = REPO / "parishes" / "cloud_sites_2026-10-29.json"
TARGET = date(2026, 11, 8)


def _one(row: dict, accepted: set[date]) -> dict:
    url = str(row.get("url") or "")
    key = str(row.get("key") or "")
    try:
        proved = prove_this_week_file(url, accepted)
    except Exception as exc:
        return {"key": key, "url": url, "error": str(exc)[:160]}
    if not proved or proved.get("date") != TARGET.isoformat():
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
