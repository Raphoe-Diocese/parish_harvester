"""Meath leftover skip unskip 05/10/2026 — recipes only, no harvest."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEATH = ROOT / "parishes" / "recipes" / "meath"


def _load(key: str) -> dict:
    return json.loads((MEATH / f"{key}.json").read_text())


class MeathLeftoverUnskipTests(unittest.TestCase):
    def test_meath_unskipped_this_week_recipes(self):
        curraha = _load("curraha")
        self.assertIsNot(curraha.get("skip"), True)
        self.assertEqual(curraha["site_type"], "http_scrape_newest_pdf")
        self.assertTrue(curraha["start_url"].endswith("/bulletin/"))
        self.assertIn("sunday", curraha["href_patterns"])

        kingscourt = _load("kingscourt")
        self.assertIsNot(kingscourt.get("skip"), True)
        self.assertEqual(kingscourt["site_type"], "wp_json_newest_media")
        self.assertIn("gyproc", kingscourt["href_skip_patterns"])

        navan = _load("navan")
        self.assertIsNot(navan.get("skip"), True)
        self.assertEqual(navan["site_type"], "http_scrape_newest_pdf")
        self.assertIn("/bulletin/", navan["post_slug_patterns"])
        self.assertFalse(navan["start_url"].endswith(".pdf"))

        kilskyre = _load("kilskyre")
        self.assertIsNot(kilskyre.get("skip"), True)
        self.assertEqual(kilskyre["site_type"], "html_text_bulletin")

        clara = _load("clara")
        self.assertIsNot(clara.get("skip"), True)
        self.assertEqual(clara["site_type"], "html_text_bulletin")
        self.assertEqual(clara["steps"][1]["pick_strategy"], "first_match")

        beauparc = _load("beauparc")
        self.assertIsNot(beauparc.get("skip"), True)
        self.assertEqual(beauparc["site_type"], "mcn_live_parish_page")
        self.assertEqual(beauparc["mcn_church_id"], 629)
        self.assertNotIn("cloudfront", beauparc["start_url"])

    def test_meath_ardcath_stays_alias_skip(self):
        ardcath = _load("ardcath")
        self.assertTrue(ardcath["skip"])
        self.assertEqual(ardcath["alias_of"], "curraha")

    def test_meath_tullamore_and_already_harvestable_untouched(self):
        tullamore = _load("tullamore")
        self.assertTrue(tullamore["skip"])
        self.assertNotIn("alias_of", tullamore)
        for key in (
            "ashbourne",
            "athboy",
            "dunboyne",
            "dunshaughlin",
            "kells",
            "kilbeggan",
            "mullingar",
            "ratoath",
            "trim",
        ):
            recipe = _load(key)
            self.assertIsNot(recipe.get("skip"), True)


if __name__ == "__main__":
    unittest.main()
