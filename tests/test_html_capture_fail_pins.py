"""HTML-capture fails 13/11/2026: St Carlo HTML pin; four honest stale."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.recipe_brain import missed_week_should_retry


def _recipe(rel: str) -> dict:
    return json.loads(Path(rel).read_text(encoding="utf-8-sig"))


class HtmlCaptureFailPinsTests(unittest.TestCase):
    def _assert_st_carlo_wordpress_print(self, rel: str, parish_key: str) -> None:
        recipe = _recipe(rel)
        page = "https://www.stcarloacutisparish.ie/newsletter-7th-8th-november-2026/"
        self.assertEqual(recipe["parish_key"], parish_key)
        self.assertEqual(recipe["start_url"], page)
        self.assertEqual(recipe["steps"][0]["url"], page)
        self.assertNotIn("newsletter-8th-november-2026", recipe["start_url"])
        self.assertNotIn("newsletter-7th-november-2026/", recipe["start_url"])
        self.assertNotIn("31st-october-1st-november", recipe["start_url"])
        self.assertNotIn("newsletter-14th-15th-november-2026", recipe["start_url"])
        self.assertNotIn("category/newsletters", recipe["start_url"])
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))

    def test_ardfinnan_pins_7th_8th_html_not_invented_8th(self) -> None:
        self._assert_st_carlo_wordpress_print(
            "parishes/recipes/waterford_and_lismore/ardfinnan.json", "ardfinnan"
        )

    def test_st_carlo_twins_pin_same_7th_8th_html(self) -> None:
        self._assert_st_carlo_wordpress_print(
            "parishes/recipes/waterford_and_lismore/newcastlefourmilewater.json",
            "newcastlefourmilewater",
        )
        self._assert_st_carlo_wordpress_print(
            "parishes/recipes/waterford_and_lismore/touraneena.json", "touraneena"
        )

    def test_abbeyknockmoy_is_honest_stale_all_saints_not_8th(self) -> None:
        recipe = _recipe("parishes/recipes/tuam/abbeyknockmoy.json")
        self.assertTrue(recipe.get("skip"))
        self.assertIn("abbeyknockmoykillererinparishes.ie", recipe["start_url"])
        self.assertNotIn("08.11.26", recipe["start_url"])
        self.assertNotIn("8th-november", recipe["start_url"])
        self.assertIn("01.11.26", recipe.get("example_url") or "")
        self.assertFalse(missed_week_should_retry(recipe))

    def test_ballyphehane_skip_not_family_news_html(self) -> None:
        recipe = _recipe("parishes/recipes/cork_and_ross/ballyphehane.json")
        self.assertEqual(recipe["parish_key"], "ballyphehane")
        self.assertTrue(recipe.get("skip"))
        self.assertNotEqual(recipe["start_url"].rstrip("/"), "https://familyofparishes.ie/news")
        self.assertFalse(missed_week_should_retry(recipe))

    def test_dennkilmore_skip_parked_site(self) -> None:
        recipe = _recipe("parishes/recipes/kilmore/dennkilmore.json")
        self.assertTrue(recipe.get("skip"))
        self.assertNotIn("newsletter-8th-november", recipe["start_url"])
        self.assertFalse(missed_week_should_retry(recipe))

    def test_doneraile_skip_key_is_not_doneraileparish(self) -> None:
        recipe = _recipe("parishes/recipes/cloyne/doneraile.json")
        self.assertEqual(recipe["parish_key"], "doneraile")
        self.assertTrue(recipe.get("skip"))
        self.assertNotIn("newsletter-8th-november", recipe["start_url"])
        self.assertFalse(missed_week_should_retry(recipe))
        self.assertFalse(Path("parishes/recipes/cloyne/doneraileparish.json").exists())


if __name__ == "__main__":
    unittest.main()
