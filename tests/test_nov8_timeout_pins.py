"""08/11/2026 timeout pins: direct file, not predicted_dated_pdf."""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from harvester.replay import _looks_like_direct_document_url, _same_dated_image_group


TARGET = date(2026, 11, 8)


def _recipe(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class Nov8TimeoutPinTests(unittest.TestCase):
    def test_ballyfermot_pins_8_november_sunday_message(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/ballyfermotassumption.json")
        self.assertIn(
            "Sunday-Messge-32nd-Sunday-in-Ordinary-time-8-Nov-2026-A4-Double.pdf",
            recipe["start_url"],
        )
        self.assertNotIn("1-Nov", recipe["start_url"])
        self.assertNotIn("SHARE", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")

    def test_ballymun_pins_8_november_webp(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/ballymunroad.json")
        self.assertIn("/2026/11/Newsletter-8-Nov-26.webp", recipe["start_url"])
        self.assertTrue(_looks_like_direct_document_url(recipe["start_url"]))
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertFalse(recipe["skip"])

    def test_churchtown_pins_proved_hash_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/churchtown.json")
        self.assertIn(
            "/2026/11/churchtown-auto-8c9056d343f7583cb7ff273d592cecd688e25151b674411fa05efb7d75b30aff.pdf",
            recipe["start_url"],
        )
        self.assertNotIn("/newsletter/", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe["site_type"], "wp_json_newest_media")
        self.assertEqual(recipe["playbook_type"], "direct_download")

    def test_claregalway_stacks_both_8_november_pages(self) -> None:
        recipe = _recipe("parishes/recipes/galway/claregalway.json")
        self.assertIn("Newsletter-8th-November-26-page-001.jpg", recipe["start_url"])
        self.assertIn(
            "Newsletter-8th-November-26-page-002.jpg",
            recipe["fallback_document_urls"][0],
        )
        grouped = _same_dated_image_group(
            [recipe["example_url"], recipe["fallback_document_urls"][0]]
        )
        self.assertEqual(len(grouped), 2)
        self.assertTrue(grouped[0].endswith("page-001.jpg"))
        self.assertTrue(grouped[1].endswith("page-002.jpg"))
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")

    def test_cloyne_pins_8_november_file(self) -> None:
        recipe = _recipe("parishes/recipes/cloyne/cloyneparish.json")
        self.assertIn("Newsletter-8th-November-2026-All-Saints.pdf", recipe["start_url"])
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertFalse(recipe["skip"])

    def test_crossmolina_pins_8_november_not_15(self) -> None:
        recipe = _recipe("parishes/recipes/killala/crossmolina.json")
        self.assertIn(
            "/2026/11/8th-November-Crossmolina-Parish-Newsletter.pdf",
            recipe["start_url"],
        )
        self.assertNotIn("15th-November", recipe["start_url"])
        self.assertNotIn("churchtv.ie", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")

    def test_same_dated_images_do_not_mix_weeks(self) -> None:
        mixed = _same_dated_image_group(
            [
                "https://claregalwayparish.ie/wp-content/uploads/2026/11/Newsletter-8th-November-26-page-001.jpg",
                "https://claregalwayparish.ie/wp-content/uploads/2026/10/Newsletter-1st-November-26-page-001.jpg",
            ]
        )
        self.assertEqual(mixed, [])
        self.assertEqual(
            TARGET.isoformat(),
            "2026-11-08",
        )


if __name__ == "__main__":
    unittest.main()
