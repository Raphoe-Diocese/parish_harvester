from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.fetcher import FetchResult, ParishEntry, _fetch_entry


class HtmlLinkCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_html_link_skips_pdf_scrape(self) -> None:
        entry = ParishEntry(
            key="parishofsionmills",
            display_name="Sion Mills",
            pattern="html_link",
            content_type="html_link",
            example_url="http://www.parishofsionmills.com/news.html",
        )
        scrape_mock = AsyncMock(
            return_value=FetchResult(
                key="parishofsionmills",
                display_name="Sion Mills",
                status="ok",
                url="http://www.parishofsionmills.com/pdf/PRAYERSFORPROTECTIONANDBLESSING.pdf",
                file_type="pdf",
            )
        )
        forced = FetchResult(
            key="parishofsionmills",
            display_name="Sion Mills",
            status="ok",
            url="http://www.parishofsionmills.com/news.html",
            file_type="html_render",
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            missing_recipe = out_dir / "recipes" / "parishofsionmills.json"
            with (
                patch("harvester.fetcher.recipe_path_for", return_value=missing_recipe),
                patch("harvester.fetcher._scrape_and_download", scrape_mock),
                patch(
                    "harvester.fetcher._try_force_html_to_pdf",
                    AsyncMock(return_value=forced),
                ),
                patch(
                    "harvester.fetcher._scrape_seed_urls",
                    return_value=["http://www.parishofsionmills.com/news.html"],
                ),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 6, 21),
                    browser=object(),
                    manual_overrides={},
                )

        scrape_mock.assert_not_called()
        self.assertEqual("ok", result.status)
        self.assertEqual("html_render", result.file_type)


if __name__ == "__main__":
    unittest.main()
