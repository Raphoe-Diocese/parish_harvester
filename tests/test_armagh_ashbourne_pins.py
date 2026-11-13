"""Step 5/6: Armagh 8 Nov PDF in /2026/11/; Ashbourne 32nd Sunday under /2025/08/."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


class ArmaghAshbournePinTests(unittest.TestCase):
    def test_armagh_pins_8th_november_in_november_folder(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/armagh/armaghparish.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("/2026/11/8th-November.pdf", recipe["start_url"])
        self.assertNotIn("/2026/09/", recipe["start_url"])
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["playbook_type"], "direct_download")

    def test_donaghmoyne_pins_32nd_allsaints_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/clogher/donaghmoyne.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("32nd-of-Ordinary-Time-All-Saints-Sunday-08th-November-2026.pdf", recipe["start_url"])
        self.assertNotIn("21st-of-Ordinary-Time", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_roslea_pins_8_november_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/clogher/roslea.json").read_text(encoding="utf-8-sig")
        )
        self.assertIn("Bulletin-Sunday-8th-November-2026.pdf", recipe["start_url"])
        self.assertNotIn("category/parish-bulletin", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_ashbourne_pins_32nd_sunday_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/meath/ashbourne.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("32nd-sunday-a-2026.pdf", recipe["start_url"])
        self.assertIn("/2025/08/", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotIn("newsletters", recipe["start_url"])


if __name__ == "__main__":
    unittest.main()
