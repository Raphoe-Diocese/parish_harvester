"""Kerry leftover skip hunt 05/10/2026 — Kenmare + St John's unskip, no dated pin."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path("parishes/recipes/kerry")


class KerryLeftoverUnskipTests(unittest.TestCase):
    def test_kenmare_scrapes_listing_not_diocese_card(self) -> None:
        recipe = json.loads((ROOT / "kenmare.json").read_text())
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertIn("kenmareparish.ie", recipe["start_url"])
        self.assertIn("/other-information/newsletters/", recipe["start_url"])
        self.assertNotIn("40-Sunday-4th-October-2026", recipe["steps"][0]["url"])
        self.assertIn("4th-October-2026", recipe["example_url"])

    def test_stjohns_uses_wp_json_not_html_listing(self) -> None:
        recipe = json.loads((ROOT / "stjohnskerry.json").read_text())
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["site_type"], "wp_json_newest_media")
        self.assertEqual(recipe["start_url"], "https://stjohns.ie/")
        self.assertNotIn("041026-newsletter", recipe["steps"][0]["url"])
        self.assertIn("041026-newsletter-.pdf", recipe["example_url"])

    def test_pr284_keys_not_rewritten_inactive(self) -> None:
        for key in (
            "abbeydorney",
            "annascaul",
            "ardfert",
            "ballydonoghue",
            "castlemaine",
            "dromtariffe",
            "duagh",
            "fossa",
            "glenbeigh",
            "kilgarvan",
            "milltownkerry",
            "spakerry",
            "traleestbrendans",
        ):
            recipe = json.loads((ROOT / f"{key}.json").read_text())
            self.assertFalse(recipe.get("skip"), key)
            self.assertNotEqual(recipe.get("site_type"), "link_only", key)


if __name__ == "__main__":
    unittest.main()
