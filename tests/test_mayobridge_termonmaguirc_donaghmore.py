"""Step 5/6: pin this-week PDFs so Cloudflare/listing hangs do not win."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


class PasteHitRecipePinsTests(unittest.TestCase):
    def test_termonmaguirc_pins_thirty_second_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/armagh/termonmaguirc.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("Thirty-Second-Sunday-in-Ordinary-Time-8-Nov-2026.pdf", recipe["start_url"])
        self.assertNotIn("Twenty-Sixth", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["steps"][0]["action"], "download")

    def test_mayobridge_pins_8_november_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/dromore/mayobridge.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("Parish-Bulletin-8-November-2026.pdf", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotIn("parish-newsletter", recipe["start_url"])

    def test_donaghmore_pins_pdf_with_ignore_https(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/dromore/donaghmore.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn("Donaghmore-Bulletin-8th-November-2026.pdf", recipe["start_url"])
        self.assertTrue(recipe.get("ignore_https_errors"))
        self.assertEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_milltown_pins_8_november_pdf(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/dublin/milltowndublin.json").read_text(
                encoding="utf-8-sig"
            )
        )
        self.assertIn(
            "Weekly-Bulletin-Sunday-November-8th-2026.pdf", recipe["start_url"]
        )
        self.assertEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotIn("/newsletter/", recipe["start_url"])

    def test_mohill_pins_7th_november_html(self) -> None:
        recipe = json.loads(
            Path("parishes/recipes/ardagh/mohill.json").read_text(encoding="utf-8-sig")
        )
        self.assertIn("newsletter-7th-november-2026", recipe["start_url"])
        self.assertNotIn("newsletter-8th-november", recipe["start_url"])
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))


if __name__ == "__main__":
    unittest.main()
