"""Tests for harvester.scoreboard — read-only harvest health helper."""
from __future__ import annotations

import json
from pathlib import Path

from harvester.scoreboard import build_scoreboard, format_scoreboard


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_scoreboard_counts_and_watchlist(tmp_path: Path) -> None:
    status_path = tmp_path / "parish_status.json"
    report_path = tmp_path / "report.json"
    _write(
        status_path,
        {
            "target_date": "2026-07-26",
            "generated_at": "2026-08-01T13:40:48+00:00",
            "summary": {"total": 5, "ok": 1, "actionable": 3, "disabled": 1},
            "parishes": {
                "okparish": {
                    "outcome": "ok",
                    "category": "ok",
                    "actionable": False,
                    "display_name": "OK Parish",
                    "diocese": "Raphoe Diocese",
                },
                "staleparish": {
                    "outcome": "stale",
                    "category": "bulletin too old (recipe worked)",
                    "actionable": True,
                    "display_name": "Stale Parish",
                    "diocese": "Derry Diocese",
                },
                "timeoutparish": {
                    "outcome": "failed",
                    "category": "timeout",
                    "actionable": True,
                    "display_name": "Timeout Parish",
                    "diocese": "Down & Connor Diocese",
                },
                "disabledparish": {
                    "outcome": "disabled",
                    "category": "disabled",
                    "actionable": False,
                    "display_name": "Disabled Parish",
                    "diocese": "Raphoe Diocese",
                },
                "ballymoneyparish": {
                    "outcome": "failed",
                    "category": "timeout",
                    "actionable": True,
                    "display_name": "Ballymoney",
                    "diocese": "Down & Connor Diocese",
                },
            },
        },
    )
    _write(
        report_path,
        {
            "target_date": "2026-07-26",
            "summary": {
                "downloaded": 1,
                "failed": 2,
                "skipped": 0,
                "stale_rejected": 0,
            },
        },
    )

    data = build_scoreboard(
        status_path=status_path,
        report_path=report_path,
        watchlist=("ballymoneyparish", "missingparish"),
    )

    assert data["target_date"] == "2026-07-26"
    assert data["total_parishes"] == 5
    assert data["downloaded"] == 1
    assert data["ok"] == 1
    assert data["actionable"] == 3
    assert data["stale_but_working"] == 1
    assert data["disabled"] == 1
    assert data["top_failure_categories"][0] == ("timeout", 2)
    assert data["by_diocese"]["Raphoe Diocese"]["ok"] == 1
    assert data["by_diocese"]["Derry Diocese"]["stale_but_working"] == 1

    watch = {row["key"]: row for row in data["recently_fixed"]}
    assert watch["ballymoneyparish"]["status"] == "PENDING"
    assert watch["missingparish"]["status"] == "MISSING"

    text = format_scoreboard(data)
    assert "Harvest Success Scoreboard" in text
    assert "26/07/2026" in text
    assert "Ballymoney" in text
