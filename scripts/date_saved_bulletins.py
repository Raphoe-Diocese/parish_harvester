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


def _pdf_for_key(bulletins_dir: Path, key: str) -> Path | None:
    for pdf in (bulletins_dir / f"{key}.pdf", bulletins_dir / "current" / f"{key}.pdf"):
        if pdf.is_file():
            return pdf
    return None


def _in_week_saved_date(
    pdf: Path,
    target: date,
    url: str,
    week_start: date,
    week_end: date,
) -> tuple[date | None, str]:
    found, way = saved_bulletin_issue_date(pdf, target=target, url=url)
    if found is None or not (week_start <= found <= week_end):
        return None, way
    return found, way


def apply_saved_dates(
    status_path: Path,
    bulletins_dir: Path,
    report_path: Path | None = None,
) -> dict[str, object]:
    """Fill blank ok rows when a real issue date is inside the harvest week.

    Writes report.json (downloaded rows) when *report_path* is set, then
    parish_status.json, only when at least one date was found. Never stamps
    the harvest Sunday on an undated file.
    """
    data: dict = {}
    if status_path.is_file():
        loaded = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    report: dict | None = None
    if report_path is not None and report_path.is_file():
        loaded_report = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(loaded_report, dict):
            report = loaded_report
    target_raw = str(data.get("target_date") or "").strip()
    if not target_raw and report is not None:
        target_raw = str(report.get("target_date") or "").strip()
    if not target_raw:
        return {
            "dated": 0,
            "target": "",
            "on_sunday": 0,
            "ways": {},
            "rows": [],
        }
    target = date.fromisoformat(target_raw)
    week_start, week_end = week_window(target)
    parishes = data.get("parishes") or {}
    rows: list[dict[str, str]] = []
    ways: dict[str, int] = {}
    dated_keys: set[str] = set()

    def _record(key: str, found: date, way: str) -> None:
        iso = found.isoformat()
        uk = format_uk_date(iso)
        ways[way] = ways.get(way, 0) + 1
        rows.append({"key": key, "uk": uk, "way": way})
        dated_keys.add(key)
        print(f"{key} {uk} {way}")

    if report is not None:
        changed_report = False
        for item in report.get("downloaded") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("parish") or "").strip()
            if not key or item.get("bulletin_date"):
                continue
            pdf = _pdf_for_key(bulletins_dir, key)
            if pdf is None:
                continue
            found, way = _in_week_saved_date(
                pdf,
                target,
                str(item.get("url") or ""),
                week_start,
                week_end,
            )
            if found is None:
                continue
            item["bulletin_date"] = found.isoformat()
            item["bulletin_date_uk"] = format_uk_date(found.isoformat())
            changed_report = True
            _record(key, found, way)
        if changed_report:
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

    status_changed = False
    for key, row in parishes.items():
        if not isinstance(row, dict) or row.get("outcome") != "ok":
            continue
        if row.get("bulletin_date"):
            continue
        pdf = _pdf_for_key(bulletins_dir, key)
        if pdf is None:
            continue
        found, way = _in_week_saved_date(
            pdf,
            target,
            str(row.get("url") or ""),
            week_start,
            week_end,
        )
        if found is None:
            continue
        row["bulletin_date"] = found.isoformat()
        row["bulletin_date_uk"] = format_uk_date(found.isoformat())
        status_changed = True
        if key not in dated_keys:
            _record(key, found, way)
    if status_changed:
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
    report = REPO / "Bulletins" / "report.json"
    summary = apply_saved_dates(
        REPO / "parishes" / "parish_status.json",
        REPO / "Bulletins",
        report_path=report if report.is_file() else None,
    )
    print(json.dumps({
        "dated": summary["dated"],
        "target": summary["target"],
        "on_sunday": summary["on_sunday"],
        "ways": summary["ways"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
