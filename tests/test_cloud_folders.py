from __future__ import annotations

import unittest
from datetime import date

from harvester.cloud_folders import (
    cloud_folder_date_tokens,
    detect_cloud_date_format,
    format_cloud_folder_label,
    is_cloud_folder_url,
    parse_yy_mm_dd,
    recipe_uses_cloud_folder,
    rewrite_cloud_folder_click_step,
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


if __name__ == "__main__":
    unittest.main()
