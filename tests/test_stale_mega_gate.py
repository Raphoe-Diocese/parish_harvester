"""Stale referee gate: last-week PDFs must leave downloaded and the mega stitch."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from reportlab.pdfgen import canvas

from harvester.bulletin_freshness import (
    apply_freshness_safety_net,
    build_mega_stitch_results,
    reclassify_stale_downloaded_in_report,
)
from harvester.fetcher import FetchResult


def _heading_pdf(path: Path, *lines: str) -> None:
    c = canvas.Canvas(str(path))
    y = 700
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.save()


class ReclassifyStaleDownloadedTests(unittest.TestCase):
    TARGET = date(2026, 10, 4)

    def test_dated_last_week_url_leaves_downloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            pdf = current / "ballincollig.pdf"
            _heading_pdf(pdf, "Parish Newsletter 20 September 2026")
            report = {
                "target_date": "2026-10-04",
                "downloaded": [
                    {
                        "parish": "ballincollig",
                        "display_name": "Ballincollig",
                        "url": "https://theparishioner.ie/images/newsletter/26-09-20.pdf",
                        "file": "ballincollig.pdf",
                        "bulletin_date": "2026-09-20",
                    },
                    {
                        "parish": "inistioge",
                        "display_name": "Inistioge",
                        "url": (
                            "https://inistiogeparish.ie/wp-content/uploads/2026/10/"
                            "45.-Twenty-Seventh-Sunday-in-Ordinary-Time-04.10.26.pdf"
                        ),
                        "file": "inistioge.pdf",
                        "bulletin_date": "2026-10-04",
                    },
                ],
                "stale_rejected": [],
                "html_links": [],
                "skipped": [],
                "failed": [],
            }
            (current / "inistioge.pdf").write_bytes(b"%PDF-1.4 stub")
            rejected = reclassify_stale_downloaded_in_report(
                report, self.TARGET, current_dir=current
            )
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["key"], "ballincollig")
            self.assertEqual(
                [row["parish"] for row in report["downloaded"]],
                ["inistioge"],
            )
            self.assertEqual(report["stale_rejected"][0]["parish"], "ballincollig")
            self.assertFalse(pdf.exists())
            self.assertEqual(report["summary"]["downloaded"], 1)
            self.assertEqual(report["summary"]["stale_rejected"], 1)


class BuildMegaStitchResultsTests(unittest.TestCase):
    TARGET = date(2026, 10, 4)

    def test_orphan_pdf_on_disk_is_not_stitched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "current"
            current.mkdir()
            orphan = current / "last_week_orphan.pdf"
            _heading_pdf(orphan, "Parish Newsletter 13 September 2026")
            fresh = current / "inistioge.pdf"
            _heading_pdf(fresh, "Parish Newsletter 4 October 2026")
            report = {
                "target_date": "2026-10-04",
                "downloaded": [
                    {
                        "parish": "inistioge",
                        "display_name": "Inistioge",
                        "url": (
                            "https://inistiogeparish.ie/wp-content/uploads/2026/10/"
                            "Newsletter-4th-Oct-2026.pdf"
                        ),
                        "file": "inistioge.pdf",
                        "bulletin_date": "2026-10-04",
                    }
                ],
                "stale_rejected": [],
            }
            stubs = build_mega_stitch_results(report, current, self.TARGET)
            self.assertEqual([r.key for r in stubs], ["inistioge"])
            self.assertTrue(orphan.exists())  # left alone; not in mega

    def test_empty_url_old_heading_rejected_from_stitch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "current"
            current.mkdir()
            pdf = current / "aghyaran.pdf"
            _heading_pdf(
                pdf,
                "Sunday 13 September 2026",
                "WEST TYRONE PARISH NEWSLETTER",
            )
            report = {
                "target_date": "2026-10-04",
                "downloaded": [
                    {
                        "parish": "aghyaran",
                        "display_name": "Aghyaran",
                        "url": "",
                        "file": "aghyaran.pdf",
                    }
                ],
                "stale_rejected": [],
            }
            stubs = build_mega_stitch_results(report, current, self.TARGET)
            self.assertEqual(stubs, [])
            self.assertEqual(report["downloaded"], [])
            self.assertEqual(report["stale_rejected"][0]["parish"], "aghyaran")
            self.assertFalse(pdf.exists())


class SafetyNetEmptyUrlTests(unittest.TestCase):
    TARGET = date(2026, 10, 4)

    def test_empty_url_with_old_pdf_heading_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "castlederg.pdf"
            _heading_pdf(
                pdf,
                "Sunday 13 September 2026",
                "PARISH NEWSLETTER",
            )
            result = FetchResult(
                key="castlederg",
                display_name="Castlederg",
                status="ok",
                url="",
                file_path=pdf,
            )
            queue = Path(tmp) / "retry_queue.json"
            payload = apply_freshness_safety_net(
                [result], self.TARGET, retry_queue_path=queue
            )
            self.assertTrue(result.is_stale)
            self.assertEqual(len(payload["rejected_from_mega"]), 1)
            self.assertFalse(pdf.exists())
            self.assertTrue(queue.exists())
            data = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual(data["rejected_from_mega"][0]["key"], "castlederg")


if __name__ == "__main__":
    unittest.main()
