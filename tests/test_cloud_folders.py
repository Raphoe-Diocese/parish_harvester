from __future__ import annotations

import unittest
from datetime import date

from harvester.cloud_folders import (
    cloud_folder_date_tokens,
    detect_cloud_date_format,
    format_cloud_folder_label,
    is_cloud_folder_url,
    newest_yy_mm_dd_label,
    parse_yy_mm_dd,
    recipe_uses_cloud_folder,
    rewrite_cloud_folder_click_step,
    rewrite_year_folder_click_step,
)
from harvester.utils import extract_date_from_string


class CloudFolderTests(unittest.TestCase):
    def test_parse_yy_mm_dd_2026(self) -> None:
        self.assertEqual(parse_yy_mm_dd("26.06.14.pdf"), date(2026, 6, 14))

    def test_parse_yy_mm_dd_future_years(self) -> None:
        self.assertEqual(parse_yy_mm_dd("27.06.14"), date(2027, 6, 14))
        self.assertEqual(parse_yy_mm_dd("28.01.05.pdf"), date(2028, 1, 5))
        self.assertEqual(parse_yy_mm_dd("29.12.31.pdf"), date(2029, 12, 31))

    def test_format_label_rolls_with_target_year(self) -> None:
        self.assertEqual(format_cloud_folder_label(date(2027, 6, 14)), "27.06.14.pdf")
        self.assertEqual(format_cloud_folder_label(date(2030, 3, 8), with_pdf=False), "30.03.08")

    def test_extract_date_from_string_yy_mm_dd(self) -> None:
        self.assertEqual(extract_date_from_string("folder/26.06.14.pdf"), date(2026, 6, 14))
        self.assertEqual(extract_date_from_string("29.01.05"), date(2029, 1, 5))

    def test_extract_date_from_string_dd_mm_yy_dot_disambiguation(self) -> None:
        # stbrigidsparishbelfast.org 2026-08-09: UK-convention DD.MM.YY dot
        # filenames collide with the Drive-folder YY.MM.DD dot shape above.
        # "09.08.26" read as YY.MM.DD is a bogus 2009-08-26; read as DD.MM.YY
        # it's the genuinely current 2026-08-09. Both readings are tried and
        # the more plausible (later-year) one wins, without breaking the
        # locked YY.MM.DD Drive-folder cases above.
        self.assertEqual(
            extract_date_from_string("Parish-Bulletin-09.08.26-FOR-PRINTING.pdf"),
            date(2026, 8, 9),
        )
        # Ballymena unpadded D.M.YY (16.8.26 / 9.8.26)
        self.assertEqual(
            extract_date_from_string("16.8.26-20th-Sunday.pdf"),
            date(2026, 8, 16),
        )
        self.assertEqual(
            extract_date_from_string("9.8.26-19th-Sunday.pdf"),
            date(2026, 8, 9),
        )
        # Kilmore Newsletter-DD.MM.YYYY.pdf — 4-digit year must win over 08.20.26
        self.assertEqual(
            extract_date_from_string("Newsletter-23.08.2026.pdf"),
            date(2026, 8, 23),
        )

    def test_extract_date_from_string_dashed_yy_mm_dd_ballymoney(self) -> None:
        # ballymoneyparish.com names files YY-MM-DDpdf.pdf. Reading only as
        # DD-MM-YY made 26-08-16 look like 2016-08-26 and 26-08-23 look like
        # 2023-08-26, so this week's bulletin was rejected as stale.
        self.assertEqual(
            extract_date_from_string("26-08-16pdf.pdf"),
            date(2026, 8, 16),
        )
        self.assertEqual(
            extract_date_from_string(
                "https://www.ballymoneyparish.com/media/other/31871/26-08-23pdf.pdf"
            ),
            date(2026, 8, 23),
        )
        # Limavady / Claudy UK DD-MM-YY must still win (later year).
        self.assertEqual(extract_date_from_string("16-8-26.pdf"), date(2026, 8, 16))
        self.assertEqual(extract_date_from_string("9-8-26.docx"), date(2026, 8, 9))

    def test_detect_cloud_date_format(self) -> None:
        self.assertEqual(detect_cloud_date_format("26.06.14.pdf"), "YY.MM.DD")
        self.assertIsNone(detect_cloud_date_format("bulletin.pdf"))

    def test_is_cloud_folder_url(self) -> None:
        self.assertTrue(
            is_cloud_folder_url(
                "https://drive.google.com/drive/folders/1RjeEY_AYy62pRNWmVmDeINfHVqkPyCsw"
            )
        )
        self.assertFalse(
            is_cloud_folder_url(
                "https://drive.google.com/file/d/1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa/view"
            )
        )

    def test_is_cloud_folder_url_onedrive_id_after_other_params(self) -> None:
        # "?cid=...&id=..." — the id param isn't first, so a "?id=" substring
        # check misses it even though this is a genuine OneDrive folder link.
        self.assertTrue(
            is_cloud_folder_url("https://onedrive.live.com/?cid=ABC123&id=ABC123%211234")
        )

    def test_is_cloud_folder_url_1drv_single_file_not_a_folder(self) -> None:
        # /b/ and /u/ 1drv.ms short links are single-file shares — these
        # should go through direct document download, not folder-row picking.
        self.assertFalse(is_cloud_folder_url("https://1drv.ms/b/s!AhCn12345"))
        self.assertFalse(is_cloud_folder_url("https://1drv.ms/u/s!AhCn12345"))

    def test_is_cloud_folder_url_1drv_folder_still_detected(self) -> None:
        self.assertTrue(is_cloud_folder_url("https://1drv.ms/f/s!AhCn12345"))

    def test_rewrite_click_step_for_target_sunday(self) -> None:
        step = {
            "action": "click",
            "text": "26.06.14.pdf",
            "selector": ":has-text('26.06.14')",
        }
        rewritten = rewrite_cloud_folder_click_step(step, date(2028, 6, 11))
        self.assertEqual(rewritten["text"], "28.06.11.pdf")
        self.assertIn("28.06.11", rewritten["selector"])
        self.assertTrue(rewritten.get("cloud_folder"))

    def test_rewrite_click_step_selector_is_row_scoped_not_bare(self) -> None:
        """A bare, unscoped :has-text(...) primary selector matches the first
        ancestor anywhere on the page containing that date substring — which
        in a real Google Drive folder listing can be a large layout
        container, not the specific file row, so .first clicks whatever
        that happens to be instead of the intended row (found 2026-08-09,
        Bruckless: this picked an unrelated January file for an August
        target). The primary selector must stay scoped to the file row."""
        step = {
            "action": "click",
            "text": "26.06.28.pdf",
            "cloud_folder": True,
            "date_format": "YY.MM.DD",
            "selector": "[role=\"row\"]:has-text('26.06.28.pdf')",
        }
        rewritten = rewrite_cloud_folder_click_step(step, date(2026, 8, 9))
        self.assertTrue(rewritten["selector"].startswith('[role="row"]'))
        self.assertIn("26.08.09", rewritten["selector"])
        self.assertNotIn(rewritten["selector"], rewritten["fallback_selectors"])

    def test_cloud_folder_date_tokens(self) -> None:
        tokens = cloud_folder_date_tokens(date(2027, 6, 14))
        self.assertIn("27.06.14.pdf", tokens)

    def test_recipe_uses_cloud_folder(self) -> None:
        steps = [
            {"action": "goto", "url": "https://drive.google.com/drive/folders/abc"},
            {"action": "click", "text": "26.06.14.pdf", "date_format": "YY.MM.DD"},
            {"action": "download"},
        ]
        self.assertTrue(recipe_uses_cloud_folder(steps))

    def test_rewrite_year_folder_click_step(self) -> None:
        step = {
            "action": "click",
            "text": "2026",
            "year_folder": True,
            "selector": "[role=\"row\"]:has-text('2026')",
        }
        rewritten = rewrite_year_folder_click_step(step, date(2028, 1, 9))
        self.assertEqual(rewritten["text"], "2028")
        self.assertIn("2028", rewritten["selector"])

    def test_newest_yy_mm_dd_label(self) -> None:
        self.assertEqual(
            newest_yy_mm_dd_label(
                [
                    "26.08.02.pdf Shared 30 Jul",
                    "26.08.16.pdf Shared 14 Aug",
                    "26.08.09.pdf Shared 6 Aug",
                    "folder 2026",
                ]
            ),
            "26.08.16.pdf",
        )
        self.assertIsNone(newest_yy_mm_dd_label(["README", "notes.txt"]))


if __name__ == "__main__":
    unittest.main()
