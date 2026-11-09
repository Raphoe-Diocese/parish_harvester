#!/usr/bin/env python3
"""GitHub entry: fast scan, then deep scan. Not for Frank's laptop."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.parish_scan import REPORT_NAME, run_parish_scan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan parish websites for this Sunday")
    parser.add_argument("--mode", choices=("fast", "deep", "both"), default="both")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    summary = run_parish_scan(
        mode=args.mode,
        workers=max(1, args.workers),
        apply=args.apply,
        report_path=REPO / "parishes" / REPORT_NAME,
    )
    brief = {key: summary[key] for key in ("mode", "scanned", "wins", "taught", "missed", "left_out")}
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
