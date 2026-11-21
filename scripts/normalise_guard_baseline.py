#!/usr/bin/env python3
"""Compare current coverage against a *quality-adjusted* previous baseline.

The 15 November report falsely counted directory HTML, future-week issues and
a repeated diocesan safeguarding document as successful parish bulletins.
Do not disable the 10% coverage-drop guard when correcting those mistakes:
remove only these demonstrably invalid previous successes from its snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from harvester.report_quality import (
    reject_directory_downloads,
    reject_future_dated_downloads,
    reject_known_diocesan_admin_downloads,
)


def normalise(previous: dict, report: dict) -> int:
    if not isinstance(previous, dict) or not isinstance(report, dict):
        return 0
    if not report.get("target_date") or previous.get("target_date") != report.get("target_date"):
        return 0
    original = {
        str(row["parish"]) for row in report.get("downloaded", [])
        if isinstance(row, dict) and row.get("parish")
    }
    clean = {
        "target_date": report.get("target_date"),
        "downloaded": list(report.get("downloaded") or []),
        "failed": list(report.get("failed") or []),
        "stale_rejected": list(report.get("stale_rejected") or []),
        "summary": dict(report.get("summary") or {}),
    }
    reject_directory_downloads(clean)
    reject_future_dated_downloads(clean)
    reject_known_diocesan_admin_downloads(clean)
    accepted = {
        str(row["parish"]) for row in clean.get("downloaded", [])
        if isinstance(row, dict) and row.get("parish")
    }
    demonstrably_invalid = original - accepted
    entries = previous.get("parishes") or {}
    if not isinstance(entries, dict):
        return 0
    corrected = 0
    for key in demonstrably_invalid:
        item = entries.get(key)
        if isinstance(item, dict) and item.get("outcome") == "ok":
            item["outcome"] = "invalid_previous_download"
            item["category"] = "invalid_previous_download"
            item["error"] = "Prior report wrongly accepted an administrative, directory or future-week document"
            corrected += 1
    summary = previous.setdefault("summary", {})
    if isinstance(summary, dict):
        summary["ok"] = sum(
            isinstance(row, dict) and row.get("outcome") == "ok"
            for row in entries.values()
        )
        summary["quality_adjusted_previous_false_positives"] = corrected
    return corrected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.status.exists() or not args.report.exists():
        print("No compatible previous status/report, keeping original coverage guard")
        return 0
    status = json.loads(args.status.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    removed = normalise(status, report)
    args.status.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"Coverage guard baseline: excluded {removed} proven false positives; 10% drop limit retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
