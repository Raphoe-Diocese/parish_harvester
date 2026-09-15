from __future__ import annotations

import unittest

from harvester.report import merge_diocese_reports


class MergeDioceseReportsTests(unittest.TestCase):
    def test_unions_parishes_and_last_report_wins(self) -> None:
        raphoe = {
            "target_date": "2026-09-13",
            "downloaded": [{"parish": "raphoecathedral", "file": "a.pdf"}],
            "failed": [{"parish": "oldfail", "error": "x"}],
            "html_links": [],
            "skipped": [],
            "stale_rejected": [],
        }
        derry = {
            "target_date": "2026-09-14",
            "downloaded": [{"parish": "oldfail", "file": "fixed.pdf"}],
            "failed": [],
            "html_links": [{"parish": "htmlonly", "url": "https://ex"}],
            "skipped": [],
            "stale_rejected": [],
        }
        merged = merge_diocese_reports([raphoe, derry])
        self.assertEqual(merged["target_date"], "2026-09-14")
        self.assertEqual(merged["summary"]["downloaded"], 2)
        self.assertEqual(merged["summary"]["failed"], 0)
        self.assertEqual(merged["summary"]["html_links"], 1)
        keys = {item["parish"] for item in merged["downloaded"]}
        self.assertEqual(keys, {"raphoecathedral", "oldfail"})


if __name__ == "__main__":
    unittest.main()
