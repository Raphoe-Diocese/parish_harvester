#!/usr/bin/env python3
"""Date blank saved bulletins from the shared issue-date reader. Runs on GitHub."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.bulletin_freshness import saved_bulletin_issue_date, week_window  # noqa: E402
from harvester.utils import format_uk_date  # noqa: E402


def apply_saved_dates(status_path: Path, bulletins_dir: Path) -> dict[str, object]:
    """Fill blank ok rows when a real issue date is inside the harvest week.

    Writes parish_status.json only when at least one date was found.
    """
    data = json.loads(status_path.read_text(encoding="utf-8"))
    target = date.fromisoformat(str(data.get("target_date") or "2026-11-08"))
    week_start, week_end = week_window(target)
    parishes = data.get("parishes") or {}
    rows: list[dict[str, str]] = []
    ways: dict[str, int] = {}
    for key, row in parishes.items():
        if not isinstance(row, dict) or row.get("outcome") != "ok":
            continue
        if row.get("bulletin_date"):
            continue
        pdf = bulletins_dir / f"{key}.pdf"
        if not pdf.is_file():
            continue
        found, way = saved_bulletin_issue_date(
            pdf,
            target=target,
            url=str(row.get("url") or ""),
        )
        if found is None or not (week_start <= found <= week_end):
            continue
        row["bulletin_date"] = found.isoformat()
        row["bulletin_date_uk"] = format_uk_date(found.isoformat())
        ways[way] = ways.get(way, 0) + 1
        rows.append({"key": key, "uk": row["bulletin_date_uk"], "way": way})
        print(f"{key} {row['bulletin_date_uk']} {way}")
    if rows:
        status_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    on_sunday = sum(1 for item in rows if item["uk"] == format_uk_date(target.isoformat()))
    return {
        "dated": len(rows),
        "target": target.isoformat(),
        "on_sunday": on_sunday,
        "ways": ways,
        "rows": rows,
    }


def main() -> int:
    summary = apply_saved_dates(REPO / "parishes" / "parish_status.json", REPO / "Bulletins")
    print(json.dumps({
        "dated": summary["dated"],
        "target": summary["target"],
        "on_sunday": summary["on_sunday"],
        "ways": summary["ways"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
