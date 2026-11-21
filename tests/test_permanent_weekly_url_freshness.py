"""A live weekly PDF may be replaced at an ancient WordPress uploads URL."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

from harvester.bulletin_freshness import (
    freshness_verdict_for_ok_result,
    reclassify_stale_downloaded_in_report,
)
from harvester.fetcher import FetchResult


class PermanentWeeklyUrlTests(unittest.TestCase):
    SUNDAY = date(2026, 11, 15)
    URL = (
        "https://www.balallyparish.ie/wp-content/uploads/2020/06/"
        "Newsletter-14th-15th-November.pdf"
    )

    @staticmethod
    def _pdf(path: Path, issue: str) -> None:
        page = canvas.Canvas(str(path))
        page.drawString(55, 760, "PARISH NEWSLETTER")
        page.drawString(55, 740, issue)
        page.drawString(55, 720, "Mass times and parish notices")
        page.save()

    def _result(self, path: Path) -> FetchResult:
        return FetchResult(
            key="balally", display_name="Balally", status="ok",
            url=self.URL, file_path=path, file_type="pdf",
        )

    def test_current_masthead_overrides_old_wp_upload_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "balally.pdf"
            self._pdf(pdf, "Sunday 15 November 2026")
            with patch("harvester.bulletin_freshness._parish_status_row", return_value=None):
                verdict = freshness_verdict_for_ok_result(self._result(pdf), self.SUNDAY)
            self.assertEqual(verdict.status, "fresh")
            self.assertEqual(verdict.extracted_date, self.SUNDAY)
            self.assertEqual(verdict.reason, "printed_current_issue_overrides_old_source")

    def test_outdated_masthead_does_not_override_old_wp_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "balally.pdf"
            self._pdf(pdf, "Sunday 8 November 2026")
            with patch("harvester.bulletin_freshness._parish_status_row", return_value=None):
                verdict = freshness_verdict_for_ok_result(self._result(pdf), self.SUNDAY)
            self.assertEqual(verdict.status, "stale")

    def test_report_uses_proved_week_not_original_folder_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "current"
            current.mkdir()
            pdf = current / "balally.pdf"
            self._pdf(pdf, "Sunday 15 November 2026")
            report = {
                "downloaded": [{
                    "parish": "balally", "display_name": "Balally",
                    "url": self.URL, "file": "balally.pdf", "file_type": "pdf",
                    "bulletin_date": "2020-06-14",
                }],
                "stale_rejected": [], "failed": [], "skipped": [], "html_links": [],
                "summary": {"downloaded": 1},
            }
            with patch("harvester.bulletin_freshness._parish_status_row", return_value=None):
                rejected = reclassify_stale_downloaded_in_report(
                    report, self.SUNDAY, current_dir=current
                )
            self.assertEqual(rejected, [])
            self.assertEqual(report["downloaded"][0]["bulletin_date"], "2026-11-15")
            self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
