#!/usr/bin/env python3
"""Push a harvest commit to main, keeping newly generated harvest files.

Used by ``.github/workflows/harvest.yml`` after the harvest commit. Mega PDFs,
diocese HTML pages, and harvest JSON cannot always merge; add/add or content
conflicts on those generated paths take this harvest's files and continue.
Recipes and harvester source are not auto-overwritten.

Usage:
  python scripts/push_harvest_results.py
  python scripts/push_harvest_results.py --remote origin --branch main
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.mega_pdf_git import push_with_mega_conflict_retry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    push_with_mega_conflict_retry(
        REPO,
        remote=args.remote,
        branch=args.branch,
        attempts=args.attempts,
    )


if __name__ == "__main__":
    main()
