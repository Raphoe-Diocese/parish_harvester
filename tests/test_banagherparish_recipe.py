from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "parishes" / "recipes" / "derry" / "banagherparish.json"


class BanagherParishRecipeTests(unittest.TestCase):
    def test_recipe_picks_newest_newsletter_from_homepage_top(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "banagherparish")
        self.assertEqual(payload.get("site_type"), "joomla_dropfiles")
        self.assertEqual(payload.get("start_url"), "https://www.banagherparish.com/")
        self.assertEqual(payload.get("bulletin_layout", {}).get("position"), "top")

        steps = payload.get("steps") or []
        self.assertGreaterEqual(len(steps), 2)
        click = steps[0]
        self.assertEqual(click.get("pick_strategy"), "newest_dated")
        self.assertEqual(click.get("bulletin_position"), "top")
        self.assertIn("/Newsletters/", click.get("href") or "")
        self.assertNotIn("28th-June-2026", json.dumps(payload.get("steps") or []))
        self.assertNotIn("/395/", json.dumps(payload.get("steps") or []))

        notes = " ".join(payload.get("do_not") or []).lower()
        self.assertIn("bottom", notes)


if __name__ == "__main__":
    unittest.main()
