"""Leftover 08/11/2026 PDF pins: wordpress direct_download, not predicted_dated_pdf."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def _recipe(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class Leftover0811PinTests(unittest.TestCase):
    def _assert_wordpress_direct(self, recipe: dict, needle: str) -> None:
        self.assertIn(needle, recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe.get("skip"), True)
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertIn(needle, recipe["steps"][0]["url"])
        self.assertEqual(recipe["steps"][1]["action"], "download")
        self.assertIn(needle, recipe["steps"][1]["url"])

    def test_mulhuddart_pins_ugd_8_november_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/mulhuddart.json")
        self._assert_wordpress_direct(
            recipe, "a0b31f_664f57d81a59457ca7a9501409534181.pdf"
        )
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.stlukesparishd15.com"
        )

    def test_stjohnsfallsroad_pins_8_november_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/down_and_connor/stjohnsfallsroad.json")
        self._assert_wordpress_direct(recipe, "Sunday-8th-Nov-2026-ws.pdf")
        self.assertIn("/2022/06/", recipe["start_url"])
        self.assertNotIn("index.php/bulletin", recipe["start_url"])
        self.assertNotIn("1st-Nov", recipe["start_url"])

    def test_gurranabraher_pins_32nd_nov_8_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/cork_and_ross/gurranabraher.json")
        self._assert_wordpress_direct(
            recipe, "Gurranabraher-32nd-Ordinary-Time-Nov-8th-2026-A.pdf"
        )
        self.assertNotIn("category/newsletters", recipe["start_url"])
        self.assertNotIn("All-Saints", recipe["start_url"])
        self.assertNotIn("Nov-1st", recipe["start_url"])

    def test_salthill_pins_parish_news_nov_8_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/galway/salthill.json")
        self._assert_wordpress_direct(recipe, "Parish-News-Nov-8th-2026-1.pdf")
        self.assertNotEqual(recipe["start_url"].rstrip("/"), "https://salthillparish.ie")
        self.assertNotIn("September-13th", recipe["start_url"])


if __name__ == "__main__":
    unittest.main()
