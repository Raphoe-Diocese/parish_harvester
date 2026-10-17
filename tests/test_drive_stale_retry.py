"""A saved Google Drive PDF must not be opened again in the browser."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.bulletin_freshness import FreshnessVerdict
from harvester.fetcher import (
    FetchResult,
    ParishEntry,
    _is_direct_drive_download_url,
    _recover_stale_bulletin,
    _scrape_and_download,
)

_DRIVE_FILE = (
    "https://drive.usercontent.google.com/download"
    "?id=1IWiKy8p3_-5xX_SYMu1-M2THO5FVaSyH&export=download"
)


class DriveStaleRetryTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_drive_file_download(self) -> None:
        self.assertTrue(_is_direct_drive_download_url(_DRIVE_FILE))
        self.assertTrue(
            _is_direct_drive_download_url(
                "https://drive.google.com/uc?export=download&id=abc"
            )
        )
        self.assertFalse(
            _is_direct_drive_download_url(
                "https://drive.google.com/drive/folders/1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK"
            )
        )

    async def test_stale_drive_file_is_not_opened_in_the_browser(self) -> None:
        result = FetchResult(
            key="drive-1rjeey-ayy",
            display_name="Bruckless",
            status="ok",
            url=_DRIVE_FILE,
            file_type="pdf",
        )
        entry = ParishEntry(
            key="drive-1rjeey-ayy",
            display_name="Bruckless",
            pattern="H",
            content_type="pdf",
            example_url=_DRIVE_FILE,
            bulletin_page=(
                "https://drive.google.com/drive/folders/"
                "1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK"
            ),
        )
        verdict = FreshnessVerdict(
            status="stale",
            extracted_date=date(2026, 10, 4),
            reason="date_behind_of_target",
        )
        with (
            patch(
                "harvester.fetcher.freshness_after_unknown_url",
                return_value=verdict,
            ),
            patch(
                "harvester.fetcher._scrape_and_download",
                new_callable=AsyncMock,
            ) as scrape,
        ):
            out = await _recover_stale_bulletin(
                result,
                entry,
                date(2026, 10, 11),
                Path("unused.pdf"),
                browser=None,  # type: ignore[arg-type]
                recipe_meta={},
                host_profile={},
            )
        scrape.assert_not_called()
        self.assertTrue(out.is_stale)
        self.assertEqual(out.diagnosis.get("failure_stage"), "stale_rejected")
        self.assertIn("2026-10-04", out.error)

    async def test_scrape_refuses_drive_download_url(self) -> None:
        entry = ParishEntry(
            key="drive-1rjeey-ayy",
            display_name="Bruckless",
            pattern="H",
            content_type="pdf",
            example_url=_DRIVE_FILE,
        )
        out = await _scrape_and_download(
            entry,
            date(2026, 10, 11),
            _DRIVE_FILE,
            Path("unused.pdf"),
            browser=None,  # type: ignore[arg-type]
        )
        self.assertEqual(out.status, "error")
        self.assertIn("not opened in the browser", out.error)
