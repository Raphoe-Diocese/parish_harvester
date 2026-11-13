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

    def test_claudy_pins_9_november_docx_not_listing(self) -> None:
        recipe = _recipe("parishes/recipes/derry/parishofclaudy.json")
        self._assert_wordpress_direct(recipe, "NEWSLETTER 9-11-26.docx")
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertTrue(recipe["steps"][1].get("use_captured_url"))
        self.assertNotIn("8-11-26", recipe["start_url"])
        self.assertNotIn("15-11-26", recipe["start_url"])
        self.assertNotIn("25-10-26", recipe["start_url"])
        self.assertNotIn("weekly-bulletin.html", recipe["start_url"])
        self.assertNotIn("financial statement", recipe["start_url"].lower())

    def test_stoliver_pins_8th_nov_pdf_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/down_and_connor/stoliverplunkettparish.json")
        self._assert_wordpress_direct(recipe, "Bulletin-8th-Nov-26.pdf")
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertNotIn("15th-November-2026", recipe["start_url"])
        self.assertNotIn("1st-Nov-26", recipe["start_url"])
        self.assertNotIn("25-Oct-26", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"),
            "https://stoliverplunkettparish.ie/bulletins",
        )

    def test_ardfinnan_print_to_pdf_is_wordpress_not_scrape(self) -> None:
        recipe = _recipe("parishes/recipes/waterford_and_lismore/ardfinnan.json")
        self.assertIn("newsletter-7th-8th-november-2026", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))
        self.assertNotIn("newsletter-14th-15th-november-2026", recipe["start_url"])

    def test_emly_pins_8th_november_docx_not_listing(self) -> None:
        recipe = _recipe("parishes/recipes/cashel_and_emly/emly.json")
        self._assert_wordpress_direct(
            recipe, "Emly-Parish-Bulletin-8th-November-2026.docx"
        )
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertNotIn("Octaber", recipe["start_url"])
        self.assertNotIn("category/parish-bulletin", recipe["start_url"])

    def test_wexford_stacks_8_november_jpegs_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/ferns/wexford.json")
        self.assertIn("Sunday-November-8th-1-scaled.jpg", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_images")
        fallbacks = recipe.get("fallback_document_urls") or []
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-2-scaled.jpg",
            fallbacks,
        )
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-3-scaled.jpg",
            fallbacks,
        )
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-4-scaled.jpg",
            fallbacks,
        )
        self.assertEqual(int(recipe["image_count"]), 4)
        self.assertNotIn("Sunday-November-15th", recipe["start_url"])
        self.assertNotIn("Sunday-November-15th", json.dumps(fallbacks))
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://wexfordparish.com"
        )

    def test_dkr_pins_8_november_pdf_not_predicted(self) -> None:
        recipe = _recipe("parishes/recipes/limerick/donaghmoreknockearoxboro.json")
        self._assert_wordpress_direct(recipe, "Newsletter-2026-11-08.pdf")
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("/2026/10/", recipe["start_url"])
        self.assertNotIn("2026-11-01", recipe["start_url"])
        self.assertNotIn("useful-links/newsletters", recipe["start_url"])

    def test_shanagolden_pins_7th_8th_nov_pdf_not_archive(self) -> None:
        recipe = _recipe(
            "parishes/recipes/limerick/shanagoldenrobertstownfoynes.json"
        )
        self._assert_wordpress_direct(recipe, "NL-7th-and-8th-Nov.-2026.pdf")
        self.assertNotIn("newsletter-archive", recipe["start_url"])
        self.assertNotIn("31st-Oct", recipe["start_url"])
        self.assertNotIn("1st-Nov", recipe["start_url"])


if __name__ == "__main__":
    unittest.main()
