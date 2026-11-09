#!/usr/bin/env python3
"""Date saved bulletins from the words on the front page. Runs on GitHub."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.bulletin_freshness import heading_date_in_pdf, week_window  # noqa: E402
from harvester.utils import format_uk_date  # noqa: E402


def main() -> int:
    status_path = REPO / "parishes" / "parish_status.json"
    data = json.loads(status_path.read_text(encoding="utf-8"))
    target = date.fromisoformat(str(data.get("target_date") or "2026-11-08"))
    week_start, week_end = week_window(target)
    parishes = data.get("parishes") or {}
    changed = 0
    for key, row in parishes.items():
        if not isinstance(row, dict) or row.get("outcome") != "ok":
            continue
        if row.get("bulletin_date"):
            continue
        pdf = REPO / "Bulletins" / f"{key}.pdf"
        if not pdf.is_file():
            continue
        found = heading_date_in_pdf(pdf, target=target)
        if found is None or not (week_start <= found <= week_end):
            continue
        row["bulletin_date"] = found.isoformat()
        row["bulletin_date_uk"] = format_uk_date(found.isoformat())
        changed += 1
        print(f"{key} {row['bulletin_date_uk']}")
    print(json.dumps({"dated": changed, "target": target.isoformat()}))
    if changed:
        status_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
