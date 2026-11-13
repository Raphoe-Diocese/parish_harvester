"""13/11/2026: Dublin predicted_dated_pdf misses. Pin proved files. Not predicted."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def _load(rel: str) -> dict:
    return json.loads((Path("parishes/recipes") / rel).read_text(encoding="utf-8-sig"))


class Nov8DublinPredictedPinTests(unittest.TestCase):
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

    def test_sandyford_pins_8_november_pdf(self) -> None:
        recipe = _load("dublin/sandyford.json")
        self._assert_wordpress_pin(recipe, "Newsletter-2026-11-08.pdf")
        self.assertNotIn("2026-11-01", recipe["start_url"])
        self.assertNotIn("November-1st", recipe["start_url"])
        self.assertTrue(recipe["start_url"].lower().endswith(".pdf"))

    def test_foxrock_stops_predicted_8_november_404(self) -> None:
        recipe = _load("dublin/foxrock.json")
        # No 08/11 parish PDF (November-8th 404). Latest parish file is All Saints.
        self._assert_wordpress_pin(recipe, "Newsletter-November-1st-2026.pdf")
        self.assertNotIn("November-8th", recipe["start_url"])
        self.assertNotIn("Share2026", recipe["start_url"])
        self.assertNotIn("/2026/11/", recipe["start_url"])
        do_not = " ".join(recipe.get("do_not") or [])
        self.assertIn("predicted_dated_pdf", do_not)
        self.assertIn("Share", do_not)


if __name__ == "__main__":
    unittest.main()
