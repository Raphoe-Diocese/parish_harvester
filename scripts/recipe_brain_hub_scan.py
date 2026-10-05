#!/usr/bin/env python3
"""GitHub Actions entry: scan skipped parishes with remembered hub tricks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.recipe_brain import scan_skipped  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Recipe Brain skip-parish hub scan")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    wins = scan_skipped(limit=args.limit, apply=args.apply)
    print(json.dumps({"apply": args.apply, "wins": wins}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
