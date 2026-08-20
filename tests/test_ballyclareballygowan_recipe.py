from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = (
    REPO_ROOT / "parishes" / "recipes" / "down_and_connor" / "ballyclareballygowan.json"
)
NOTICEBOARD = "notice%20board.htm"


class BallyclareBallygowanRecipeTests(unittest.TestCase):
    def test_recipe_prints_permanent_noticeboard(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "ballyclareballygowan")
        self.assertIn(NOTICEBOARD, payload.get("start_url", ""))
        self.assertNotRegex(payload.get("start_url", ""), r"20\d{2}-\d{2}-\d{2}")

        steps = payload.get("steps") or []
        self.assertGreaterEqual(len(steps), 2)
        self.assertEqual(steps[0].get("action"), "goto")
        self.assertIn(NOTICEBOARD, steps[0].get("url", ""))

        print_step = steps[-1]
        self.assertIn(print_step.get("action"), ("print_to_pdf", "html"))
        self.assertTrue(print_step.get("skip_listing_nav"))
        self.assertNotIn("skip", payload)


if __name__ == "__main__":
    unittest.main()
