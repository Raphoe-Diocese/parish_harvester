"""Block publishing a harvest when the ok count drops too far.

Harvest all used to commit a thinner list over a good one. Refuse to publish
when the new ok count is more than 10 percent below the previous run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def ok_count(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return 0
    summary = data.get("summary")
    if isinstance(summary, dict) and summary.get("ok") is not None:
        try:
            return max(0, int(summary["ok"]))
        except (TypeError, ValueError):
            pass
    parishes = data.get("parishes")
    if not isinstance(parishes, dict):
        return 0
    return sum(
        1
        for row in parishes.values()
        if isinstance(row, dict) and row.get("outcome") == "ok"
    )


def guard(
    previous: Path,
    new: Path,
    *,
    max_drop_ratio: float = 0.10,
) -> tuple[bool, str]:
    """Return (ok_to_publish, message)."""
    if not previous.exists():
        return True, f"No previous status at {previous} — publish allowed."
    if not new.exists():
        return False, f"New status missing at {new} — block publish."
    before = ok_count(previous)
    after = ok_count(new)
    if before <= 0:
        return True, f"Previous ok was {before} — publish allowed (after={after})."
    floor = int(before * (1.0 - max_drop_ratio))
    if after < floor:
        return (
            False,
            (
                f"Ok count dropped too far: previous={before} new={after} "
                f"floor={floor} (max drop {max_drop_ratio:.0%}). "
                "Not publishing. OCR must not run on this harvest."
            ),
        )
    return True, f"Ok count ok: previous={before} new={after} floor={floor}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument(
        "--max-drop-ratio",
        type=float,
        default=0.10,
        help="Block when new ok is below previous * (1 - ratio). Default 0.10.",
    )
    args = parser.parse_args(argv)
    allowed, message = guard(
        args.previous,
        args.new,
        max_drop_ratio=args.max_drop_ratio,
    )
    print(message)
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
