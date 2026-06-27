from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from harvester.parish_status import build_parish_status, write_parish_status
from harvester.report import patch_report_for_parishes
from harvester.fetcher import FetchResult


class ParishStatusTests(unittest.TestCase):
    def test_builds_actionable_from_failed_and_stale(self) -> None:
        report = {
            "target_date": "2026-06-21",
            "last_patched_at": "2026-06-27T12:00:00+00:00",
            "downloaded": [{"parish": "okparish", "display_name": "OK", "url": "https://x.com"}],
            "failed": [
                {
                    "parish": "failparish",
                    "display_name": "Fail",
                    "url": "https://fail.com",
                    "error": "Recipe replay failed: timeout",
                    "last_tested_at": "2026-06-27T12:00:00+00:00",
                }
            ],
            "stale_rejected": [
                {
                    "parish": "staleparish",
                    "display_name": "Stale",
                    "url": "https://stale.com",
                    "error": "Stale bulletin rejected for mega PDF (bulletin date 2026-06-07, too_old)",
                    "last_tested_at": "2026-06-27T12:00:00+00:00",
                }
            ],
            "html_links": [],
            "skipped": [],
        }
        status = build_parish_status(
            report,
            consecutive_failures={"failparish": 3, "staleparish": 2},
            disabled_keys={"disabledparish"},
        )
        self.assertEqual(status["schema_version"], 1)
        self.assertIn("failparish", status["actionable_keys"])
        self.assertIn("staleparish", status["actionable_keys"])
        self.assertNotIn("okparish", status["actionable_keys"])
        self.assertEqual(status["parishes"]["staleparish"]["category"], "bulletin too old (recipe worked)")
        self.assertEqual(status["parishes"]["failparish"]["consecutive_failures"], 3)

    def test_write_after_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parishes_dir = tmp_path / "parishes"
            parishes_dir.mkdir()
            report_json = tmp_path / "report.json"
            report_txt = tmp_path / "report.txt"
            current_dir = tmp_path / "current"
            current_dir.mkdir()
            (parishes_dir / "consecutive_failures.json").write_text('{"xparish": 1}', encoding="utf-8")

            result = FetchResult(
                key="xparish",
                display_name="X Parish",
                status="error",
                url="https://example.com/",
                error="timeout",
            )
            patch_report_for_parishes(
                [result],
                report_json,
                report_txt,
                date(2026, 6, 21),
                current_dir=current_dir,
            )
            status = write_parish_status(
                report_path=report_json,
                output_path=parishes_dir / "parish_status.json",
                parishes_dir=parishes_dir,
            )
            self.assertIn("xparish", status["actionable_keys"])
            on_disk = json.loads((parishes_dir / "parish_status.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["parishes"]["xparish"]["outcome"], "failed")


if __name__ == "__main__":
    unittest.main()
