from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from harvester.fetcher import FetchResult
from harvester.report import patch_report_for_parishes, reconcile_report_with_recipes


class PatchReportTests(unittest.TestCase):
    def test_patches_existing_failed_parish_to_downloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_json = tmp_path / "report.json"
            report_txt = tmp_path / "report.txt"
            current_dir = tmp_path / "current"
            current_dir.mkdir()
            pdf = current_dir / "threepatrons.pdf"
            pdf.write_bytes(b"%PDF-1.4")

            report_json.write_text(
                json.dumps(
                    {
                        "target_date": "2026-06-14",
                        "summary": {
                            "downloaded": 0,
                            "html_links": 0,
                            "skipped": 0,
                            "failed": 1,
                            "stale_rejected": 0,
                        },
                        "downloaded": [],
                        "html_links": [],
                        "skipped": [],
                        "failed": [
                            {
                                "parish": "threepatrons",
                                "display_name": "Three Patrons",
                                "url": "https://example.com/old",
                                "error": "Recipe finished without downloading",
                            }
                        ],
                        "stale_rejected": [],
                    }
                ),
                encoding="utf-8",
            )

            result = FetchResult(
                key="threepatrons",
                display_name="Three Patrons",
                status="ok",
                url="https://example.com/new.pdf",
                file_path=pdf,
            )
            target = date(2026, 6, 14)

            patched = patch_report_for_parishes(
                [result],
                report_json,
                report_txt,
                target,
                current_dir=current_dir,
            )

            self.assertIsNotNone(patched)
            self.assertEqual(patched["summary"]["failed"], 0)
            self.assertEqual(patched["summary"]["downloaded"], 1)
            self.assertEqual(patched["failed"], [])
            self.assertEqual(patched["downloaded"][0]["parish"], "threepatrons")

            on_disk = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["summary"]["failed"], 0)
            self.assertTrue(report_txt.exists())

    def test_creates_report_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_json = tmp_path / "report.json"
            report_txt = tmp_path / "report.txt"
            current_dir = tmp_path / "current"
            current_dir.mkdir()

            result = FetchResult(
                key="clonleighparish",
                display_name="Clonleigh",
                status="error",
                url="https://example.com/",
                error="timeout",
            )
            target = date(2026, 6, 14)

            patched = patch_report_for_parishes(
                [result],
                report_json,
                report_txt,
                target,
                current_dir=current_dir,
            )

            self.assertIsNotNone(patched)
            self.assertEqual(patched["summary"]["failed"], 1)
            self.assertEqual(patched["failed"][0]["parish"], "clonleighparish")

    def test_reconcile_moves_inactive_failed_parishes_to_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parishes_dir = tmp_path / "parishes"
            recipes_dir = parishes_dir / "recipes" / "derry"
            recipes_dir.mkdir(parents=True)
            (recipes_dir / "parishofstjohncoleraine.json").write_text(
                json.dumps(
                    {
                        "parish_key": "parishofstjohncoleraine",
                        "display_name": "Coleraine (St John)",
                        "status": "inactive",
                        "skip": True,
                        "reason": "Website DNS no longer resolves.",
                    }
                ),
                encoding="utf-8",
            )

            report = {
                "target_date": "2026-06-14",
                "summary": {
                    "downloaded": 0,
                    "html_links": 0,
                    "skipped": 0,
                    "failed": 1,
                    "stale_rejected": 0,
                },
                "downloaded": [],
                "html_links": [],
                "skipped": [],
                "failed": [
                    {
                        "parish": "parishofstjohncoleraine",
                        "display_name": "Coleraine (St John)",
                        "url": "https://www.parishofstjohncoleraine.com/",
                        "error": "Website DNS no longer resolves.",
                    }
                ],
                "stale_rejected": [],
            }

            reconciled = reconcile_report_with_recipes(report, parishes_dir=parishes_dir)
            self.assertEqual(reconciled["summary"]["failed"], 0)
            self.assertEqual(reconciled["summary"]["skipped"], 1)
            self.assertEqual(reconciled["skipped"][0]["parish"], "parishofstjohncoleraine")


if __name__ == "__main__":
    unittest.main()
