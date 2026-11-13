"""Pin this-week PDFs for timeout parishes, or HONEST STALE when no PDF exists."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class TimeoutParishPinTests(unittest.TestCase):
    def test_churchtown_pins_8_november_auto_pdf(self) -> None:
        recipe = load("parishes/recipes/dublin/churchtown.json")
        self.assertIn(
            "churchtown-auto-8c9056d343f7583cb7ff273d592cecd688e25151b674411fa05efb7d75b30aff.pdf",
            recipe["start_url"],
        )
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("newsletter-2026-11-01", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertEqual(recipe["steps"][-1]["action"], "download")

    def test_ballyfermot_pins_32nd_sunday_newsletter(self) -> None:
        recipe = load("parishes/recipes/dublin/ballyfermotassumption.json")
        self.assertIn("32nd-Sunday-OT-2026-1.pdf", recipe["start_url"])
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("All-Saints-1-Nov", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertEqual(recipe["steps"][-1]["action"], "download")

    def test_cloyne_pins_8th_november_pdf(self) -> None:
        recipe = load("parishes/recipes/cloyne/cloyneparish.json")
        self.assertIn("Newsletter-8th-November-2026-All-Saints.pdf", recipe["start_url"])
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertNotIn("/2026/10/", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertEqual(recipe["steps"][-1]["action"], "download")

    def test_booterstown_honest_stale_not_all_saints_pdf(self) -> None:
        recipe = load("parishes/recipes/dublin/booterstown.json")
        notes = " ".join(recipe.get("operator_notes") or [])
        self.assertIn("HONEST STALE", notes)
        self.assertNotIn("Sun-1-November-2026", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe["start_url"].lower().endswith(".pdf"))

    def test_ballymunroad_honest_stale_no_pdf(self) -> None:
        recipe = load("parishes/recipes/dublin/ballymunroad.json")
        notes = " ".join(recipe.get("operator_notes") or [])
        self.assertIn("HONEST STALE", notes)
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe["start_url"].lower().endswith(".pdf"))

    def test_claregalway_honest_stale_jpeg_not_pdf(self) -> None:
        recipe = load("parishes/recipes/galway/claregalway.json")
        notes = " ".join(recipe.get("operator_notes") or [])
        self.assertIn("HONEST STALE", notes)
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe["start_url"].lower().endswith(".pdf"))
        self.assertNotIn("1st-November", recipe["start_url"])


if __name__ == "__main__":
    unittest.main()
