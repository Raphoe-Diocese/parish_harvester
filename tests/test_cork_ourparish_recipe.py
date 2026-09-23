from __future__ import annotations

import json
from pathlib import Path
import unittest

from harvester.utils import extract_date_from_string


REPO = Path(__file__).resolve().parent.parent
RECIPE = REPO / "parishes" / "recipes" / "cork_and_ross" / "carrigaline.json"


class OurParishFamilyRecipeTests(unittest.TestCase):
    def test_harvests_family_pdf_once_without_pinning_the_date(self) -> None:
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        self.assertEqual(recipe["parish_key"], "carrigaline")
        self.assertEqual(recipe["diocese"], "cork_and_ross")
        self.assertEqual(recipe["start_url"], "https://ourparish.ie/newsletters")
        self.assertEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertEqual(recipe["href_patterns"], ["/images/"])
        self.assertIn("/images/", recipe["example_url"])
        self.assertFalse(recipe["steps"][0].get("use_captured_url"))

    def test_dotted_yy_mm_dd_pdf_name_is_this_week(self) -> None:
        self.assertEqual(
            extract_date_from_string(
                "https://ourparish.ie/images/26.09.20_v2.pdf"
            ).isoformat(),
            "2026-09-20",
        )
