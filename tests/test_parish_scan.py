"""Fast and deep parish scan. No live websites."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from harvester.parish_scan import leave_reason, run_parish_scan


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_facebook_and_no_website_are_left_out() -> None:
    assert leave_reason(
        {"start_url": "https://www.facebook.com/parish", "reason": "Facebook-only"}
    ) == "facebook"
    assert leave_reason(
        {"start_url": "https://parish.ie", "reason": "No parish website on the official card."}
    ) == "no_website"
    assert leave_reason(
        {
            "start_url": "https://www.artaneparish.ie/",
            "reason": "No this-week PDF or JPEG with GET 200 and date on the file.",
        }
    ) is None


def test_fast_tries_the_page_that_worked_before(tmp_path, monkeypatch) -> None:
    recipes = tmp_path / "recipes" / "dublin"
    saved = "https://staleparish.ie/newsletter/"
    _write(
        recipes / "stale.json",
        {
            "parish_key": "staleparish",
            "skip": False,
            "status": "active",
            "site_type": "http_scrape_newest_pdf",
            "start_url": saved,
            "steps": [{"action": "goto", "url": saved}],
        },
    )
    seen: list[str] = []

    def fake_urls(_start: str):
        return [("https://staleparish.ie/current-newsletter/", "permanent_redirect_document", "current-newsletter+direct_download")]

    def fake_prove(url, _accepted):
        seen.append(url)
        if url == saved:
            return {
                "url": saved + "this-week.pdf",
                "kind": "pdf",
                "bytes": 400,
                "date": "2026-11-08",
            }
        return None

    monkeypatch.setattr("harvester.parish_scan.candidate_probe_urls", fake_urls)
    monkeypatch.setattr("harvester.parish_scan.prove_this_week_file", fake_prove)
    summary = run_parish_scan(
        mode="fast",
        workers=1,
        apply=False,
        recipes_dir=tmp_path / "recipes",
        patterns_path=tmp_path / "site_patterns.json",
        report_path=tmp_path / "report.json",
        today=date(2026, 11, 9),
    )
    assert summary["wins"] == 1
    assert seen[0] == saved


def test_fast_scan_teaches_a_missed_week(tmp_path, monkeypatch) -> None:
    recipes = tmp_path / "recipes" / "dublin"
    _write(
        recipes / "artane.json",
        {
            "parish_key": "artane",
            "skip": True,
            "status": "inactive",
            "start_url": "https://www.artaneparish.ie/",
            "reason": "No this-week PDF or JPEG with GET 200 and date on the file.",
            "steps": [{"action": "goto", "url": "https://www.artaneparish.ie/"}],
        },
    )
    _write(
        recipes / "fb.json",
        {
            "parish_key": "fbparish",
            "skip": True,
            "start_url": "https://www.facebook.com/parish",
            "reason": "Facebook-only — cannot scrape Facebook",
        },
    )

    def fake_urls(start: str):
        return [(start, "http_scrape_newest_pdf", "homepage_listing")]

    def fake_prove(url, _accepted):
        if "artane" in url:
            return {
                "url": "https://www.artaneparish.ie/bulletin.pdf",
                "kind": "pdf",
                "bytes": 1200,
                "date": "2026-11-08",
            }
        return None

    monkeypatch.setattr("harvester.parish_scan.candidate_probe_urls", fake_urls)
    monkeypatch.setattr("harvester.parish_scan.prove_this_week_file", fake_prove)
    summary = run_parish_scan(
        mode="fast",
        workers=2,
        apply=True,
        recipes_dir=tmp_path / "recipes",
        patterns_path=tmp_path / "site_patterns.json",
        report_path=tmp_path / "report.json",
        today=date(2026, 11, 9),
    )
    assert summary["left_out"]["facebook"] == 1
    assert summary["wins"] == 1
    assert summary["taught"] == 1
    saved = json.loads((recipes / "artane.json").read_text(encoding="utf-8"))
    assert saved["skip"] is False
    patterns = json.loads((tmp_path / "site_patterns.json").read_text(encoding="utf-8"))
    examples = [
        parish
        for row in patterns["patterns"].values()
        for parish in row.get("example_parishes") or []
    ]
    assert "artane" in examples


def test_deep_pass_finds_what_the_fast_pass_missed(tmp_path, monkeypatch) -> None:
    recipes = tmp_path / "recipes" / "dublin"
    _write(
        recipes / "late.json",
        {
            "parish_key": "lateparish",
            "skip": True,
            "status": "inactive",
            "start_url": "https://lateparish.ie/",
            "reason": "No this-week PDF yet.",
            "steps": [{"action": "goto", "url": "https://lateparish.ie/"}],
        },
    )

    def fake_urls(start: str):
        return [
            (f"{start}?p={i}", "http_scrape_newest_pdf", "homepage_listing")
            for i in range(4)
        ]

    def fake_prove(url, _accepted):
        if "p=3" in url:
            return {
                "url": "https://lateparish.ie/8-nov.pdf",
                "kind": "pdf",
                "bytes": 800,
                "date": "2026-11-08",
            }
        return None

    monkeypatch.setattr("harvester.parish_scan.candidate_probe_urls", fake_urls)
    monkeypatch.setattr("harvester.parish_scan.prove_this_week_file", fake_prove)
    summary = run_parish_scan(
        mode="both",
        workers=2,
        apply=True,
        recipes_dir=tmp_path / "recipes",
        patterns_path=tmp_path / "site_patterns.json",
        report_path=tmp_path / "report.json",
        today=date(2026, 11, 9),
    )
    assert summary["wins"] == 1
    assert summary["hits"][0]["parish_key"] == "lateparish"


def test_active_recipe_is_not_rewritten(tmp_path, monkeypatch) -> None:
    recipes = tmp_path / "recipes" / "dublin"
    _write(
        recipes / "old.json",
        {
            "parish_key": "oldparish",
            "skip": False,
            "status": "active",
            "start_url": "https://oldparish.ie/newsletter/",
            "steps": [{"action": "download", "url": "https://oldparish.ie/newsletter/"}],
        },
    )

    monkeypatch.setattr(
        "harvester.parish_scan.candidate_probe_urls",
        lambda start: [(start, "http_scrape_newest_pdf", "homepage_listing")],
    )
    monkeypatch.setattr(
        "harvester.parish_scan.prove_this_week_file",
        lambda url, _accepted: {
            "url": "https://oldparish.ie/newsletter/now.pdf",
            "kind": "pdf",
            "bytes": 500,
            "date": "2026-11-08",
        },
    )
    run_parish_scan(
        mode="fast",
        workers=1,
        apply=True,
        recipes_dir=tmp_path / "recipes",
        patterns_path=tmp_path / "site_patterns.json",
        report_path=tmp_path / "report.json",
        today=date(2026, 11, 9),
    )
    saved = json.loads((recipes / "old.json").read_text(encoding="utf-8"))
    assert saved["steps"][0]["action"] == "download"
    assert saved["skip"] is False
