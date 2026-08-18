"""Helpers for HTTP-scrape newest PDF and predicted dated uploads."""
from __future__ import annotations

import unittest
from datetime import date

from harvester.replay import _is_non_bulletin_url, _score_http_scrape_pdf_hrefs
from harvester.utils import predicted_dated_upload_urls, yearless_slug_date


class YearlessSlugTests(unittest.TestCase):
    def test_sunday_nth_month_uses_assume_year(self) -> None:
        url = (
            "https://milfordrathmullanparishes.ie/wp-content/uploads/"
            "Parish-Newsletter-Sunday-9th-August.pdf"
        )
        self.assertEqual(
            yearless_slug_date(url, 2026, near=date(2026, 8, 16)),
            date(2026, 8, 9),
        )

    def test_december_before_new_year_rolls_back(self) -> None:
        url = "Parish-Newsletter-28th-December.pdf"
        self.assertEqual(
            yearless_slug_date(url, 2026, near=date(2026, 1, 4)),
            date(2025, 12, 28),
        )

    def test_full_year_slug_is_not_yearless(self) -> None:
        url = "Newsletter-12th-July-2026.pdf"
        self.assertIsNone(yearless_slug_date(url, 2026, near=date(2026, 8, 16)))


class PredictedDatedUploadTests(unittest.TestCase):
    def test_newtown_pattern_rewrites_sunday_and_month_folder(self) -> None:
        example = (
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/07/"
            "Newsletter-12th-July-2026.pdf"
        )
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=5)
        self.assertEqual(
            urls[0],
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-16th-August-2026.pdf",
        )
        self.assertIn(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-16th-August-2026.docx",
            urls,
        )
        self.assertIn(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-9th-August-2026.pdf",
            urls,
        )
        self.assertIn(example, urls)

    def test_claudy_oneweb_space_variants_are_quoted(self) -> None:
        example = "http://parishofclaudy.com/onewebmedia/NEWSLETTER 21-6-26.docx"
        urls = predicted_dated_upload_urls(example, date(2026, 8, 9), weeks_back=0)
        self.assertTrue(
            any("NEWSLETTER%209-8-26.docx" in u for u in urls),
            urls[:8],
        )


class HttpScrapeScoreTests(unittest.TestCase):
    def test_picks_newest_parish_newsletter_and_skips_order_of_mass(self) -> None:
        hrefs = [
            "https://www.catholicbishops.ie/wp-content/uploads/2011/02/Order-of-Mass.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-5th-July.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-Sunday-2nd-August.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-Sunday-9th-August.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 9))
        self.assertIn("Sunday-9th-August", best_url)
        self.assertTrue(_is_non_bulletin_url(hrefs[0]))
        self.assertTrue(all("Order-of-Mass" not in url for _, url in scored))

    def test_filename_date_beats_wordpress_upload_folder(self) -> None:
        # Malin uploaded March files into /2026/04/. Folder-first dating
        # would treat 29th-March as 29/04 and beat 5th-April.
        hrefs = [
            "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-29th-March-2026.pdf",
            "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf",
            "http://malinparish.ie/wp-content/uploads/2022/02/Synod-2023.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 4, 5))
        self.assertIn("5th-April", best_url)


if __name__ == "__main__":
    unittest.main()
