from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parent.parent
RECIPE = REPO / "parishes" / "recipes" / "cork_and_ross" / "aughadown.json"


class WestCorkFamilyRecipeTests(unittest.TestCase):
    def test_harvests_family_file_once_without_pinning_the_date(self) -> None:
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        self.assertEqual(recipe["parish_key"], "aughadown")
        self.assertEqual(recipe["diocese"], "cork_and_ross")
        self.assertEqual(recipe["start_url"], "https://westcorkparishes.ie/newsletters")
        self.assertEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertEqual(recipe["href_patterns"], ["FOP-"])
        self.assertIn("FOP-", recipe["example_url"])
        self.assertFalse(recipe["steps"][0].get("use_captured_url"))
        siblings = {p.name for p in (REPO / "parishes" / "recipes" / "cork_and_ross").glob("*.json")}
        self.assertIn("aughadown.json", siblings)
        for banned in (
            "castlehavenmyross.json",
            "kilmacabea.json",
            "raththeislands.json",
            "skibbereen.json",
        ):
            self.assertNotIn(banned, siblings)
