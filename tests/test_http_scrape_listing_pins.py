"""HTTP-scrape listing fails: pin this-week PDFs; Headford stays honest stale."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def _recipe(rel: str) -> dict:
    return json.loads(Path(rel).read_text(encoding="utf-8-sig"))


class HttpScrapeListingPinTests(unittest.TestCase):
    def test_laurellodge_pins_newsletter_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/laurellodge.json")
        self.assertEqual(
            recipe["start_url"],
            "https://www.laurellodgeparish.ie/images/Newsletter/newsletter.pdf",
        )
        self.assertNotEqual(recipe["start_url"].rstrip("/"), "https://www.laurellodgeparish.ie")
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_mulhuddart_pins_8_november_ugd_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/mulhuddart.json")
        self.assertIn("a0b31f_664f57d81a59457ca7a9501409534181.pdf", recipe["start_url"])
        self.assertNotEqual(recipe["start_url"].rstrip("/"), "https://www.stlukesparishd15.com")
        self.assertNotIn("/newsletter", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_stjohnscathedral_pins_8_november_fileid(self) -> None:
        recipe = _recipe("parishes/recipes/limerick/stjohnscathedral.json")
        self.assertIn("fileID=E2080F83-25AE-47CD-A5E344B06704E699", recipe["start_url"])
        self.assertIn("/index.cfm/_api/render/file/", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.limerickcathedral.com"
        )
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_headford_does_not_pin_missing_november_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/tuam/headford.json")
        self.assertNotIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("8th-November", recipe["start_url"])
        notes = " ".join(recipe.get("operator_notes") or [])
        self.assertIn("26th-27th September 2026", notes)
        self.assertIn("No this-week file", notes)


if __name__ == "__main__":
    unittest.main()
