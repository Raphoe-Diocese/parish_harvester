from __future__ import annotations

import difflib
import re

MAX_LINES_PER_SIDE = 30


def _display_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line.strip()) for line in (text or "").splitlines() if line.strip()]


def diff_bulletins(this_week_text: str, last_week_text: str) -> dict:
    current = _display_lines(this_week_text)
    previous = _display_lines(last_week_text)
    matcher = difflib.SequenceMatcher(
        a=[line.casefold() for line in previous],
        b=[line.casefold() for line in current],
        autojunk=False,
    )
    added = []
    removed = []
    kept = 0
    for kind, left, right, start, end in matcher.get_opcodes():
        if kind == "equal":
            kept += end - start
        else:
            removed.extend(previous[left:right])
            added.extend(current[start:end])
    result = {"added_lines": added[:MAX_LINES_PER_SIDE], "removed_lines": removed[:MAX_LINES_PER_SIDE], "kept_count": kept}
    if max(len(added), len(removed)) > MAX_LINES_PER_SIDE:
        result["note"] = "truncated_to_30_lines_per_side"
    return result
