"""Batch recovery never bypasses current-week PDF and parish-identity checks."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from harvester.discovery_fallback import (
    eligible_discovery_url,
    fetch_verified_discovery_pdf,
)


class DiscoveryFallbackTests(unittest.TestCase):
    TARGET = date(2026, 11, 15)
    ORIGIN = "https://www.stpatricksbelfast.org/category/weekly-bulletins/"
    DOCUMENT = (
        "https://www.stpatricksbelfast.org/wp-content/uploads/2026/11/"
        "Bulletin-New-Paula-Sunday-15-November-2026.pdf"
    )

    def _ledger(self, path: Path, **overrides) -> None:
        row = {
            "parish": "stpatricksbelfast",
            "verdict": "candidate_verified_masthead",
            "masthead_verified": True,
            "issue_date": self.TARGET.isoformat(),
            "file_kind": "pdf",
            "document_url": self.DOCUMENT,
        }
        row.update(overrides)
        path.write_text(
            json.dumps({"target_date": self.TARGET.isoformat(), "rows": [row]}),
            encoding="utf-8",
        )

    def test_exact_same_parish_host_and_week_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            self._ledger(path)
            self.assertEqual(
                eligible_discovery_url(
                    "stpatricksbelfast", self.TARGET,
                    [self.ORIGIN], ledger_path=path
                ),
                self.DOCUMENT,
            )
            self.assertIsNone(eligible_discovery_url(
                "wrongparish", self.TARGET, [self.ORIGIN], ledger_path=path
            ))
            self.assertIsNone(eligible_discovery_url(
                "stpatricksbelfast", date(2026, 11, 22),
                [self.ORIGIN], ledger_path=path
            ))

    def test_bad_masthead_verdict_foreign_file_and_shared_host_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            for changes in (
                {"verdict": "candidate_verified_bytes_and_link_date"},
                {"masthead_verified": False},
                {"issue_date": "2026-11-08"},
                {"file_kind": "png"},
                {"document_url": "https://other-parish.ie/newsletter.pdf"},
                {"document_url": "http://www.stpatricksbelfast.org/newsletter.pdf"},
                {"document_url": "https://www.stpatricksbelfast.org/notice.jpg"},
            ):
                with self.subTest(changes=changes):
                    self._ledger(path, **changes)
                    self.assertIsNone(eligible_discovery_url(
                        "stpatricksbelfast", self.TARGET,
                        [self.ORIGIN], ledger_path=path
                    ))
            self._ledger(
                path, document_url="https://www.churchtv.ie/newsletter.pdf"
            )
            self.assertIsNone(eligible_discovery_url(
                "stpatricksbelfast", self.TARGET,
                ["https://churchtv.ie"], ledger_path=path
            ))
            self._ledger(path, document_url="https://www.dioceseofkerry.ie/wp-content/uploads/2026/11/newsletter.pdf")
            self.assertIsNone(eligible_discovery_url(
                "stpatricksbelfast", self.TARGET,
                ["https://www.dioceseofkerry.ie/parish/adrigole/"], ledger_path=path
            ))

    def test_rechecks_pdf_masthead_before_writing_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.json"
            dest = Path(tmp) / "recovered.pdf"
            self._ledger(ledger)
            pdf = b"%PDF-1.7\n" + b"A" * 9000
            with patch(
                "harvester.replay._fetch_bytes_with_retries",
                return_value=(pdf, {"content-type": "application/pdf"}),
            ) as fetch, patch(
                "harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                return_value=self.TARGET,
            ):
                result = fetch_verified_discovery_pdf(
                    "stpatricksbelfast", self.TARGET,
                    [self.ORIGIN], dest, ledger_path=ledger
                )
            self.assertEqual(result, self.DOCUMENT)
            self.assertEqual(dest.read_bytes(), pdf)
            fetch.assert_called_once()

    def test_mcn_redirect_to_another_church_is_rejected(self) -> None:
        url = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/606/NewsLetter/week.pdf"
        with tempfile.TemporaryDirectory() as tmp, patch("harvester.discovery_fallback.urlopen") as get:
            ledger = Path(tmp) / "ledger.json"
            dest = Path(tmp) / "issue.pdf"
            self._ledger(ledger, document_url=url)
            response = get.return_value.__enter__.return_value
            response.geturl.return_value = url.replace("/606/", "/607/")
            self.assertIsNone(fetch_verified_discovery_pdf(
                "stpatricksbelfast", self.TARGET, [url], dest, ledger_path=ledger
            ))
            response.read.assert_not_called()
            self.assertFalse(dest.exists())

    def test_old_pdf_body_cannot_be_rescued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.json"
            dest = Path(tmp) / "recovered.pdf"
            self._ledger(ledger)
            with patch(
                "harvester.replay._fetch_bytes_with_retries",
                return_value=(b"%PDF-1.4\n" + b"X" * 6000, {}),
            ), patch(
                "harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                return_value=date(2026, 11, 8),
            ):
                result = fetch_verified_discovery_pdf(
                    "stpatricksbelfast", self.TARGET,
                    [self.ORIGIN], dest, ledger_path=ledger
                )
            self.assertIsNone(result)
            self.assertFalse(dest.exists())

    def test_main_harvester_checks_rescue_before_denying_trained_recipe(self) -> None:
        source = (
            Path(__file__).resolve().parent.parent / "harvester" / "fetcher.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("fetch_verified_discovery_pdf,"),
            source.index('if trained_recipe:\n            print(f"  ⛔'),
        )


if __name__ == "__main__":
    unittest.main()
