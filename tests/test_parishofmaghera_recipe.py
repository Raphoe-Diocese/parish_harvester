from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = (
    REPO_ROOT / "parishes" / "recipes" / "down_and_connor" / "parishofmaghera.json"
)
BULLETIN_PAGE = "https://www.parishofmaghera.com/copy-of-contact-us-2"


class ParishOfMagheraRecipeTests(unittest.TestCase):
    def test_recipe_stacks_two_images_on_permanent_bulletin_page(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "parishofmaghera")
        self.assertEqual(payload.get("diocese"), "down_and_connor")
        self.assertEqual(payload.get("start_url"), BULLETIN_PAGE)
        self.assertTrue(payload.get("disable_stale_rescrape_fallback"))
        self.assertNotIn("skip", payload)

        steps = payload.get("steps") or []
        self.assertGreaterEqual(len(steps), 2)
        self.assertEqual(steps[0].get("action"), "goto")
        self.assertEqual(steps[0].get("url"), BULLETIN_PAGE)

        stack = steps[-1]
        self.assertEqual(stack.get("action"), "image_stack")
        self.assertEqual(stack.get("count"), 2)
        self.assertLessEqual(int(stack.get("min_short_side") or 500), 400)
        self.assertLessEqual(int(stack.get("min_long_side") or 700), 550)

        notes = " ".join(payload.get("do_not") or [])
        self.assertIn("parishofballinascreen", notes)
        self.assertNotIn("copy-of-weekly-bulletin", payload.get("start_url", ""))


if __name__ == "__main__":
    unittest.main()
