"""Helpers for HTTP-scrape newest PDF and predicted dated uploads."""
from __future__ import annotations

import unittest
from datetime import date

from harvester.replay import _is_non_bulletin_url, _resolve_download_candidates, _score_http_scrape_pdf_hrefs
from harvester.utils import (
    dropfiles_task_download_url,
    extract_mcn_church_id,
    looks_like_permanent_bulletin_url,
    mcn_newsletter_url_from_profile,
    mcn_profile_data_url,
    predicted_dated_upload_urls,
    rewrite_date_url,
    wix_dated_slug_candidates,
    yearless_slug_date,
)


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

    def test_holyfamily_parish_derry_ddmmyy_path(self) -> None:
        example = "https://www.holyfamily-parish.com/pdf/090826.pdf"
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=2)
        self.assertEqual(urls[0], "https://www.holyfamily-parish.com/pdf/160826.pdf")
        self.assertIn("https://www.holyfamily-parish.com/pdf/090826.pdf", urls)
        self.assertTrue(
            all("holy-familyparish.com" not in u for u in urls),
            urls[:6],
        )

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

    def test_liturgical_and_glenavy_filenames_score_current_week(self) -> None:
        hrefs = [
            "https://www.holy-familyparish.com/app/uploads/2026/08/Nineteenth-Sunday-in-Ordinary-Time.pdf",
            "https://www.holy-familyparish.com/app/uploads/2026/08/Twentieth-Sunday-in-Ordinary-Time.pdf",
            "https://ballymenaparish.org/wp-content/uploads/2025/01/Wedding-Parish.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 16))
        self.assertIn("Twentieth-Sunday", best_url)
        self.assertTrue(all("Wedding-Parish" not in url for _, url in scored))

    def test_old_year_liturgical_file_does_not_beat_current(self) -> None:
        hrefs = [
            "https://glenariffeparish.org/wp-content/uploads/2024/08/Twentieth-Sunday-of-Ordinary-time.pdf",
            "https://glenariffeparish.org/wp-content/uploads/2026/07/Sixteenth-Sunday-of-Ordinary-Time.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 7, 19))
        self.assertIn("2026/07/Sixteenth", best_url)

    def test_glenavy_year_monthname_day_filename(self) -> None:
        hrefs = [
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/04/2026-April-26-Fourth-Sunday-of-Easter.pdf",
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/08/2026-August-16-Twentieth-Sunday-in-Ordinary-Time.pdf",
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/08/2026-August-9-nineteenth-Sunday-in-Ordinary-Time.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 16))
        self.assertIn("August-16", best_url)


class WixDatedSlugCandidateTests(unittest.TestCase):
    def test_ballinascreen_includes_copy_of_variant(self) -> None:
        example = (
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-21_june_2026"
        )
        urls = wix_dated_slug_candidates(example, date(2026, 8, 16), weeks_back=1)
        self.assertEqual(
            urls[0],
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-16_august_2026",
        )
        self.assertEqual(
            urls[1],
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-16_august_2026",
        )
        self.assertIn(
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-9_august_2026",
            urls,
        )

    def test_copy_of_example_does_not_double_prefix(self) -> None:
        example = (
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-9_august_2026"
        )
        urls = wix_dated_slug_candidates(example, date(2026, 8, 16), weeks_back=0)
        copy_ofs = [u for u in urls if "/copy-of-copy-of-" in u]
        self.assertEqual(copy_ofs, [])
        self.assertIn(
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-16_august_2026",
            urls,
        )


class DropfilesTaskUrlTests(unittest.TestCase):
    def test_banagher_sef_to_task_download(self) -> None:
        sef = (
            "https://www.banagherparish.com/files/9/Newsletters/395/"
            "Bulletin---13th-Sunday-in-Ordinary-Time---28th-June-2026"
        )
        self.assertEqual(
            dropfiles_task_download_url(sef),
            "https://www.banagherparish.com/index.php?option=com_dropfiles"
            "&task=frontfile.download&catid=9&id=395",
        )

    def test_non_dropfiles_url_returns_none(self) -> None:
        self.assertIsNone(
            dropfiles_task_download_url(
                "https://www.banagherparish.com/information"
            )
        )


class PermanentBulletinUrlTests(unittest.TestCase):
    def test_newtown_deep_path_is_permanent(self) -> None:
        url = "https://newtownkilleaparish.ie/bulletin/raphoe/newtown-killea/"
        self.assertTrue(looks_like_permanent_bulletin_url(url))
        self.assertEqual(rewrite_date_url(url, date(2026, 8, 16)), url)
        self.assertEqual(
            _resolve_download_candidates(url, target_date=date(2026, 8, 16)),
            [url],
        )

    def test_listing_bulletin_slash_is_not_permanent(self) -> None:
        self.assertFalse(
            looks_like_permanent_bulletin_url("https://newtownkilleaparish.ie/bulletin/")
        )

    def test_predicted_august_filename_is_not_used_for_permanent_path(self) -> None:
        guessed = predicted_dated_upload_urls(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/07/Newsletter-12th-July-2026.pdf",
            date(2026, 8, 16),
            weeks_back=0,
        )
        self.assertTrue(any("Newsletter-16th-August-2026.pdf" in u for u in guessed))
        self.assertFalse(
            looks_like_permanent_bulletin_url(guessed[0]),
        )


class McnNewsletterHelperTests(unittest.TestCase):
    def test_extracts_church_id_and_profile_url(self) -> None:
        html = '<input type="hidden" value="164" id="hfChurchId" />'
        self.assertEqual(extract_mcn_church_id(html), "164")
        self.assertEqual(
            mcn_profile_data_url(
                "https://mcn.live/Camera/our-lady-of-perpetual-succour-glenfinn",
                "164",
            ),
            "https://mcn.live/Website/ProfileDataByJson/164",
        )

    def test_reads_newsletter_url_from_profile_json(self) -> None:
        payload = {
            "newsletter": {
                "newsLetterTitle": "SUNDAY NEWSLETTER FOR SUNDAY AUGUST 16th 2026",
                "newsLetterUrl": (
                    "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/"
                    "NewsLetter/fede99e0-206f-4ce5-9787-810dbbe0ceb4.pdf"
                ),
            }
        }
        self.assertTrue(
            str(mcn_newsletter_url_from_profile(payload)).endswith(".pdf")
        )
        self.assertIsNone(mcn_newsletter_url_from_profile({"newsletter": {}}))


if __name__ == "__main__":
    unittest.main()
