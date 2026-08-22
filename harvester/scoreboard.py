"""
scoreboard.py — Read-only Harvest Success Scoreboard (console helper).

Prints current harvest health from existing report.json + parish_status.json.
Does not write files, change workflows, or mutate status/report formats.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import PARISH_STATUS_JSON, REPORT_JSON
from .utils import format_uk_date

# Recently fixed parish keys — watch until a harvest newer than the fix proves them.
RECENTLY_FIXED_WATCHLIST: tuple[str, ...] = (
    "stmarysportglenone",
    "aghagallonandballinderryparish",
    "ardmoreparish",
    "ballymoneyparish",
)

_DIOCESE_ORDER: tuple[str, ...] = (
    "Raphoe Diocese",
    "Derry Diocese",
    "Down & Connor Diocese",
    "Clogher Diocese",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_stale_but_working(row: dict[str, Any]) -> bool:
    outcome = str(row.get("outcome") or "").strip().lower()
    category = str(row.get("category") or "").strip().lower()
    if outcome == "stale":
        return True
    return "bulletin too old" in category or "recipe worked" in category


def _normalize_diocese(label: str) -> str:
    raw = (label or "").strip()
    if not raw:
        return "Unknown"
    lower = raw.lower()
    if "raphoe" in lower:
        return "Raphoe Diocese"
    if "derry" in lower:
        return "Derry Diocese"
    if "down" in lower and "connor" in lower:
        return "Down & Connor Diocese"
    return raw


def build_scoreboard(
    *,
    status_path: Path | None = None,
    report_path: Path | None = None,
    watchlist: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Build a scoreboard dict from parish_status.json + report.json."""
    status = _load_json(status_path or PARISH_STATUS_JSON)
    report = _load_json(report_path or REPORT_JSON)
    watch = tuple(watchlist) if watchlist is not None else RECENTLY_FIXED_WATCHLIST

    parishes: dict[str, Any] = status.get("parishes") or {}
    if not isinstance(parishes, dict):
        parishes = {}

    status_summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    report_summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}

    total = int(status_summary.get("total") or len(parishes))
    ok_count = int(status_summary.get("ok") or 0)
    if not ok_count:
        ok_count = sum(1 for row in parishes.values() if isinstance(row, dict) and row.get("outcome") == "ok")

    downloaded = int(report_summary.get("downloaded") or ok_count)
    actionable = int(status_summary.get("actionable") or 0)
    if not actionable:
        actionable = sum(
            1 for row in parishes.values() if isinstance(row, dict) and row.get("actionable") is True
        )

    failed_report = int(report_summary.get("failed") or 0)
    skipped_report = int(report_summary.get("skipped") or 0)
    disabled = int(status_summary.get("disabled") or 0)
    if not disabled:
        disabled = sum(
            1 for row in parishes.values() if isinstance(row, dict) and row.get("outcome") == "disabled"
        )
    skipped_or_disabled = skipped_report + disabled

    stale_but_working = sum(
        1 for row in parishes.values() if isinstance(row, dict) and _is_stale_but_working(row)
    )

    fail_cats: Counter[str] = Counter()
    for row in parishes.values():
        if not isinstance(row, dict):
            continue
        if row.get("actionable") is not True:
            continue
        cat = str(row.get("category") or "unknown").strip() or "unknown"
        if cat.lower() in {"ok", "disabled", "skipped"}:
            continue
        fail_cats[cat] += 1

    by_diocese: dict[str, dict[str, int]] = {}
    for row in parishes.values():
        if not isinstance(row, dict):
            continue
        dio = _normalize_diocese(str(row.get("diocese") or ""))
        bucket = by_diocese.setdefault(
            dio,
            {
                "total": 0,
                "ok": 0,
                "actionable": 0,
                "stale_but_working": 0,
                "skipped": 0,
                "disabled": 0,
            },
        )
        bucket["total"] += 1
        outcome = str(row.get("outcome") or "").strip().lower()
        if outcome == "ok":
            bucket["ok"] += 1
        if row.get("actionable") is True:
            bucket["actionable"] += 1
        if _is_stale_but_working(row):
            bucket["stale_but_working"] += 1
        if outcome == "skipped":
            bucket["skipped"] += 1
        if outcome == "disabled":
            bucket["disabled"] += 1

    watch_rows: list[dict[str, Any]] = []
    for key in watch:
        row = parishes.get(key) if isinstance(parishes.get(key), dict) else {}
        outcome = str(row.get("outcome") or "missing")
        category = str(row.get("category") or "missing")
        if outcome == "ok" or category.lower() == "ok":
            watch_status = "PASS"
        elif not row:
            watch_status = "MISSING"
        else:
            watch_status = "PENDING"
        watch_rows.append(
            {
                "key": key,
                "display_name": row.get("display_name") or key,
                "outcome": outcome,
                "category": category,
                "actionable": bool(row.get("actionable")) if row else None,
                "status": watch_status,
            }
        )

    target_date = status.get("target_date") or report.get("target_date")
    return {
        "target_date": target_date,
        "generated_at": status.get("generated_at") or status.get("last_patched_at"),
        "total_parishes": total,
        "downloaded": downloaded,
        "ok": ok_count,
        "actionable": actionable,
        "failed_report": failed_report,
        "skipped_report": skipped_report,
        "disabled": disabled,
        "skipped_or_disabled": skipped_or_disabled,
        "stale_but_working": stale_but_working,
        "top_failure_categories": fail_cats.most_common(),
        "by_diocese": by_diocese,
        "recently_fixed": watch_rows,
    }


def format_scoreboard(data: dict[str, Any]) -> str:
    """Plain-text scoreboard for console printing."""
    lines: list[str] = []
    target = data.get("target_date")
    uk = format_uk_date(target) if target else "unknown"
    lines.append("=== Harvest Success Scoreboard ===")
    lines.append(f"Target date: {uk} ({target or 'unknown'})")
    if data.get("generated_at"):
        lines.append(f"Status generated: {data['generated_at']}")
    lines.append(f"Total parishes: {data.get('total_parishes', 0)}")
    lines.append(
        f"Downloaded / ok: {data.get('downloaded', 0)} downloaded, {data.get('ok', 0)} ok"
    )
    lines.append(
        f"Actionable / failed: {data.get('actionable', 0)} actionable"
        f" (report failed={data.get('failed_report', 0)})"
    )
    lines.append(
        f"Skipped / disabled: {data.get('skipped_or_disabled', 0)}"
        f" (skipped={data.get('skipped_report', 0)}, disabled={data.get('disabled', 0)})"
    )
    lines.append(f"Stale-but-working: {data.get('stale_but_working', 0)}")

    lines.append("Top failure categories:")
    cats = data.get("top_failure_categories") or []
    if not cats:
        lines.append("  (none)")
    else:
        for name, count in cats[:8]:
            lines.append(f"  {count:3d}  {name}")

    lines.append("Per-diocese:")
    by_dio = data.get("by_diocese") or {}
    ordered = list(_DIOCESE_ORDER) + sorted(k for k in by_dio if k not in _DIOCESE_ORDER)
    for dio in ordered:
        bucket = by_dio.get(dio)
        if not bucket:
            continue
        lines.append(
            f"  {dio}: total={bucket['total']} ok={bucket['ok']} "
            f"actionable={bucket['actionable']} stale={bucket['stale_but_working']} "
            f"skipped={bucket['skipped']} disabled={bucket['disabled']}"
        )

    lines.append("Recently fixed watchlist:")
    for row in data.get("recently_fixed") or []:
        lines.append(
            f"  {row['status']:7} {row['key']} — {row.get('display_name')} "
            f"[{row.get('category')}]"
        )
    return "\n".join(lines)


def print_scoreboard(
    *,
    status_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Build and print the scoreboard; return the data dict."""
    data = build_scoreboard(status_path=status_path, report_path=report_path)
    print(format_scoreboard(data))
    return data


def main() -> None:
    print_scoreboard()


if __name__ == "__main__":
    main()
