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
        # A2: every row, including disabled, has a non-empty last_tested_at.
        for key, row in status["parishes"].items():
            self.assertTrue(
                str(row.get("last_tested_at") or "").strip(),
                f"{key} last_tested_at empty",
            )
        self.assertEqual(
            status["parishes"]["failparish"]["last_tested_at"],
            "2026-06-27T12:00:00+00:00",
        )
        # H4: last_patched_at is another parish's stamp — must not leak.
        self.assertNotEqual(
            status["parishes"]["okparish"]["last_tested_at"],
            report["last_patched_at"],
        )
        self.assertEqual(status["parishes"]["okparish"]["last_tested_at"], status["generated_at"])
        self.assertEqual(status["parishes"]["disabledparish"]["last_tested_at"], status["generated_at"])

    def test_ok_and_stale_rows_record_bulletin_date(self) -> None:
        report = {
            "target_date": "2026-09-06",
            "downloaded": [
                {
                    "parish": "annagryparish",
                    "display_name": "Annagry",
                    "url": "https://annagryparish.ie/wp-content/uploads/2026/09/060926.pdf",
                }
            ],
            "stale_rejected": [
                {
                    "parish": "staleparish",
                    "display_name": "Stale",
                    "url": "https://stale.example/old.pdf",
                    "error": "Stale bulletin rejected for mega PDF (bulletin date 2026-08-30, too_old)",
                }
            ],
            "failed": [
                {
                    "parish": "failparish",
                    "display_name": "Fail",
                    "url": "https://fail.example/",
                    "error": "timeout",
                }
            ],
            "html_links": [],
            "skipped": [],
        }
        status = build_parish_status(report, consecutive_failures={}, disabled_keys=set())
        annagry = status["parishes"]["annagryparish"]
        self.assertEqual(annagry["outcome"], "ok")
        self.assertEqual(annagry["bulletin_date"], "2026-09-06")
        self.assertEqual(annagry["bulletin_date_uk"], "06/09/2026")
        stale = status["parishes"]["staleparish"]
        self.assertEqual(stale["outcome"], "stale")
        self.assertEqual(stale["bulletin_date"], "2026-08-30")
        self.assertEqual(stale["bulletin_date_uk"], "30/08/2026")
        self.assertIsNone(status["parishes"]["failparish"].get("bulletin_date"))

    def test_last_tested_at_keeps_previous_row_when_item_has_no_stamp(self) -> None:
        report = {
            "target_date": "2026-09-06",
            "last_patched_at": "2026-09-10T12:00:00+00:00",
            "downloaded": [{"parish": "okparish", "display_name": "OK", "url": "https://x.com"}],
            "failed": [
                {
                    "parish": "failparish",
                    "display_name": "Fail",
                    "url": "https://fail.com",
                    "error": "timeout",
                    "last_tested_at": "2026-09-10T12:00:00+00:00",
                }
            ],
            "stale_rejected": [],
            "html_links": [],
            "skipped": [],
        }
        previous = {
            "parishes": {
                "okparish": {"last_tested_at": "2026-09-09T01:07:23+00:00"},
            }
        }
        status = build_parish_status(
            report,
            consecutive_failures={},
            disabled_keys=set(),
            previous_status=previous,
        )
        self.assertEqual(
            status["parishes"]["okparish"]["last_tested_at"],
            "2026-09-09T01:07:23+00:00",
        )
        self.assertEqual(
            status["parishes"]["failparish"]["last_tested_at"],
            "2026-09-10T12:00:00+00:00",
        )

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
            self.assertTrue(str(on_disk["parishes"]["xparish"].get("last_tested_at") or "").strip())

    def test_live_recipe_without_evidence_row_is_no_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parishes_dir = tmp_path / "parishes"
            recipe_dir = parishes_dir / "recipes" / "derry"
            recipe_dir.mkdir(parents=True)
            (recipe_dir / "cappaghparish.json").write_text(
                json.dumps(
                    {
                        "parish_key": "cappaghparish",
                        "display_name": "Cappagh",
                        "start_url": "https://www.cappaghparish.com/index.html",
                        "steps": [{"action": "goto", "url": "https://www.cappaghparish.com/index.html"}],
                    }
                ),
                encoding="utf-8",
            )
            (parishes_dir / "recipes" / "raphoe").mkdir()
            (parishes_dir / "recipes" / "raphoe" / "ballintra.json").write_text(
                json.dumps(
                    {
                        "parish_key": "ballintra",
                        "display_name": "Ballintra",
                        "skip": True,
                        "steps": [{"action": "goto", "url": "https://example.com/skip"}],
                    }
                ),
                encoding="utf-8",
            )
            report = {
                "target_date": "2026-09-06",
                "downloaded": [
                    {"parish": "okparish", "display_name": "OK", "url": "https://ok.example/x.pdf"}
                ],
                "failed": [],
                "stale_rejected": [],
                "html_links": [],
                "skipped": [],
            }
            status = build_parish_status(
                report,
                parishes_dir=parishes_dir,
                consecutive_failures={},
                disabled_keys=set(),
            )
            self.assertEqual(status["parishes"]["cappaghparish"]["outcome"], "no_evidence")
            self.assertTrue(status["parishes"]["cappaghparish"]["actionable"])
            self.assertIn("cappaghparish", status["actionable_keys"])
            self.assertEqual(status["parishes"]["cappaghparish"]["diocese"], "Derry Diocese")
            self.assertNotIn("ballintra", status["parishes"])
            self.assertEqual(status["parishes"]["okparish"]["outcome"], "ok")
            self.assertNotIn("okparish", status["actionable_keys"])

    def test_harvest_note_copies_into_diagnosis_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parishes_dir = Path(tmp) / "parishes"
            recipe_dir = parishes_dir / "recipes" / "clogher"
            recipe_dir.mkdir(parents=True)
            note = (
                "Blocked from GitHub runners (WAF/403). Needs a different "
                "network. Do not re-hunt weekly."
            )
            (recipe_dir / "ederney.json").write_text(
                json.dumps(
                    {
                        "parish_key": "ederney",
                        "display_name": "Ederney",
                        "harvest_note": note,
                        "start_url": "https://culmaine.co.uk/newsletter",
                        "steps": [{"action": "print_to_pdf"}],
                    }
                ),
                encoding="utf-8",
            )
            status = build_parish_status(
                {
                    "target_date": "2026-09-06",
                    "downloaded": [],
                    "failed": [
                        {
                            "parish": "ederney",
                            "display_name": "Ederney",
                            "url": "https://culmaine.co.uk/newsletter",
                            "error": "HTTP 403",
                        }
                    ],
                    "stale_rejected": [],
                    "html_links": [],
                    "skipped": [],
                },
                parishes_dir=parishes_dir,
                consecutive_failures={},
                disabled_keys=set(),
            )
            row = status["parishes"]["ederney"]
            self.assertEqual(row["diagnosis"]["harvest_note"], note)
            self.assertTrue(str(row["error"]).startswith(note))
            self.assertIn("HTTP 403", row["error"])
            self.assertTrue(row["actionable"])
            self.assertNotEqual(row.get("skip"), True)


if __name__ == "__main__":
    unittest.main()
