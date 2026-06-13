"""Tests for bulletin freshness safety net."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from harvester.bulletin_freshness import (
    apply_freshness_safety_net,
    check_bulletin_freshness,
    extract_bulletin_date,
    mark_result_stale,
    suggest_retry_strategy,
    week_window,
)
from harvester.fetcher import FetchResult, ParishEntry


class BulletinFreshnessTests(unittest.TestCase):
    def test_extract_bulletin_date_supports_common_formats(self) -> None:
        self.assertEqual(
            extract_bulletin_date("https://x.com/bulletin_150626.pdf"),
            date(2026, 6, 15),
        )
        self.assertEqual(
            extract_bulletin_date("https://x.com/bulletin-2026-06-15.pdf"),
            date(2026, 6, 15),
        )

    def test_check_freshness_in_week_is_fresh(self) -> None:
        target = date(2026, 6, 14)  # Sunday
        url = "https://example.com/bulletin_140626.pdf"
        verdict = check_bulletin_freshness(url, target)
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_check_freshness_old_date_is_stale(self) -> None:
        target = date(2026, 6, 14)
        old = (target - timedelta(days=20)).strftime("%d%m%y")
        verdict = check_bulletin_freshness(f"https://example.com/bulletin_{old}.pdf", target)
        self.assertEqual(verdict.status, "stale")

    def test_unknown_date_is_not_auto_rejected(self) -> None:
        target = date(2026, 6, 14)
        verdict = check_bulletin_freshness("https://example.com/weekly-bulletin.pdf", target)
        self.assertEqual(verdict.status, "unknown")

    def test_mark_result_stale_sets_retry_metadata(self) -> None:
        target = date(2026, 6, 14)
        entry = ParishEntry(
            key="testparish",
            display_name="Test Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.com/old.pdf",
            bulletin_page="https://example.com/bulletins/",
        )
        result = FetchResult(
            key="testparish",
            display_name="Test Parish",
            status="ok",
            url="https://example.com/bulletin_010526.pdf",
        )
        verdict = check_bulletin_freshness(result.url, target)
        self.assertEqual(verdict.status, "stale")
        marked = mark_result_stale(result, verdict, entry=entry)
        self.assertTrue(marked.is_stale)
        self.assertEqual(marked.status, "error")
        self.assertEqual(marked.retry_strategy, "rescrape_bulletin_page")

    def test_suggest_retry_strategy_for_pattern_parish(self) -> None:
        entry = ParishEntry(
            key="p",
            display_name="P",
            pattern="B",
            content_type="pdf",
            example_url="https://x.com/a.pdf",
        )
        result = FetchResult(key="p", display_name="P", status="ok", url="https://x.com/a.pdf")
        self.assertEqual(suggest_retry_strategy(result, entry), "try_date_patterns")

    def test_apply_freshness_safety_net_writes_retry_queue(self) -> None:
        target = date(2026, 6, 14)
        old = (target - timedelta(days=30)).strftime("%Y-%m-%d")
        results = [
            FetchResult(
                key="staleone",
                display_name="Stale One",
                status="ok",
                url=f"https://example.com/bulletin-{old}.pdf",
            ),
            FetchResult(
                key="freshone",
                display_name="Fresh One",
                status="ok",
                url=f"https://example.com/bulletin-{target.isoformat()}.pdf",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "retry_queue.json"
            payload = apply_freshness_safety_net(
                results,
                target,
                retry_queue_path=queue_path,
            )
            self.assertEqual(len(payload["rejected_from_mega"]), 1)
            self.assertTrue(results[0].is_stale)
            self.assertFalse(results[1].is_stale)
            on_disk = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(len(on_disk["retry"]), 1)
            self.assertEqual(on_disk["retry"][0]["strategy"], "mistral_heal")

    def test_week_window_matches_fetcher(self) -> None:
        target = date(2026, 6, 14)
        start, end = week_window(target)
        self.assertEqual(start, target - timedelta(days=6))
        self.assertEqual(end, target)


if __name__ == "__main__":
    unittest.main()
