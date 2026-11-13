"""13/11/2026: pin this-week PDFs for HTTP-scrape misses. Not predicted_dated_pdf."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def _load(rel: str) -> dict:
    return json.loads((Path("parishes/recipes") / rel).read_text(encoding="utf-8-sig"))


class Nov8HttpScrapePinTests(unittest.TestCase):
    def _assert_wordpress_pin(self, recipe: dict, needle: str) -> None:
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertIn(needle, recipe["start_url"])
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertEqual(recipe["steps"][1]["action"], "download")
        self.assertIn(needle, recipe["steps"][0]["url"])
        self.assertIn(needle, recipe["steps"][1]["url"])
        self.assertTrue(recipe["steps"][1].get("use_captured_url"))

    def test_laurellodge_pins_current_newsletter_pdf(self) -> None:
        recipe = _load("dublin/laurellodge.json")
        self._assert_wordpress_pin(recipe, "/images/Newsletter/newsletter.pdf")
        self.assertNotEqual(recipe["start_url"], "https://www.laurellodgeparish.ie/")
        self.assertTrue(recipe["start_url"].lower().endswith(".pdf"))

    def test_stjohns_cathedral_pins_8_november_file(self) -> None:
        recipe = _load("limerick/stjohnscathedral.json")
        self._assert_wordpress_pin(
            recipe, "fileID=E2080F83-25AE-47CD-A5E344B06704E699"
        )
        self.assertNotEqual(recipe["start_url"], "https://www.limerickcathedral.com/")


if __name__ == "__main__":
    unittest.main()
