"""Recipes proved from WordPress media uploaded on or after 6 Nov 2026."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _recipe(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class Since6NovRecipeTests(unittest.TestCase):
    def test_balally_uses_wp_json_not_a_pinned_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/balally.json")
        self.assertEqual(recipe["site_type"], "wp_json_newest_media")
        self.assertTrue(recipe["start_url"].startswith("https://www.balallyparish.ie/"))
        self.assertFalse(recipe["start_url"].lower().endswith(".pdf"))
        self.assertNotIn("example_url", recipe)
        patterns = [str(p).lower() for p in recipe["href_patterns"]]
        self.assertIn("newsletter", patterns)
        self.assertIn(".pdf", patterns)
        self.assertIn("pin", " ".join(recipe.get("do_not") or []).lower())
        for step in recipe["steps"]:
            self.assertFalse(str(step.get("url") or "").lower().endswith(".pdf"))

    def test_cappoquin_uses_wp_json_not_the_july_listing(self) -> None:
        recipe = _recipe("parishes/recipes/waterford_and_lismore/cappoquin.json")
        self.assertEqual(recipe["site_type"], "wp_json_newest_media")
        self.assertFalse(recipe.get("skip"))
        self.assertNotEqual(str(recipe.get("status") or "").lower(), "inactive")
        self.assertTrue(recipe["start_url"].startswith("https://www.cappoquin.net/"))
        self.assertFalse(recipe["start_url"].lower().endswith(".pdf"))
        patterns = [str(p).lower() for p in recipe["href_patterns"]]
        self.assertIn("sun-ot", patterns)
        self.assertIn("pin", " ".join(recipe.get("do_not") or []).lower())

    def test_confey_stacks_two_listing_images(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/confey.json")
        self.assertEqual(recipe["site_type"], "http_scrape_newest_images")
        self.assertIn("sun-ot", [str(p).lower() for p in recipe["href_patterns"]])
        counts = [
            step.get("count")
            for step in recipe["steps"]
            if isinstance(step, dict) and step.get("action") == "image_stack"
        ]
        self.assertIn(2, counts)
        self.assertFalse(recipe["start_url"].lower().endswith((".jpg", ".pdf")))

    def test_confey_pattern_keeps_both_full_pages(self) -> None:
        from harvester.replay import _extract_scored_upload_images

        html = """
        <img src="https://www.confeyparish.ie/wp-content/uploads/2025/04/2026-11-08_P1-32nd-Sun-OT-1024x1448.jpg"
             srcset="https://www.confeyparish.ie/wp-content/uploads/2025/04/2026-11-08_P1-32nd-Sun-OT.jpg 1240w">
        <img src="https://www.confeyparish.ie/wp-content/uploads/2025/04/2026-11-08_P2-32nd-Sun-OT-1024x1448.jpg"
             srcset="https://www.confeyparish.ie/wp-content/uploads/2025/04/2026-11-08_P2-32nd-Sun-OT.jpg 1240w">
        <img src="https://www.confeyparish.ie/wp-content/uploads/2026/10/2026-10-25_P1-30th-Sun-OT.jpg">
        <img src="https://www.confeyparish.ie/wp-content/uploads/2026/11/2026-11-01_P1-All-Saints.jpg">
        """
        scored = _extract_scored_upload_images(
            html,
            "https://www.confeyparish.ie/newsletter/",
            href_patterns=["sun-ot"],
            target_date=date(2026, 11, 8),
        )
        best = max(found for found, _url in scored)
        week = [url for found, url in scored if found == best]
        self.assertEqual(best, date(2026, 11, 8))
        self.assertEqual(
            [url.rsplit("/", 1)[-1] for url in week],
            [
                "2026-11-08_P1-32nd-Sun-OT.jpg",
                "2026-11-08_P2-32nd-Sun-OT.jpg",
            ],
        )


if __name__ == "__main__":
    unittest.main()
