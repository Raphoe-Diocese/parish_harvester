from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from harvester.utils import clonleigh_candidate_urls


REPO_ROOT = Path(__file__).resolve().parent.parent


class ClonleighHomepageRecipeTests(unittest.TestCase):
    def test_recipe_starts_on_homepage_not_lagging_category(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "derry" / "clonleighparish.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("start_url"), "https://clonleighparish.com/")
        self.assertNotIn("category/newsletter", payload.get("start_url", ""))
        actions = [str(s.get("action") or "") for s in (payload.get("steps") or [])]
        self.assertEqual(actions, ["goto", "click", "print_to_pdf"])
        click = payload["steps"][1]
        self.assertIn("Strabane Pastoral Area Newsletter", click.get("selector", ""))

    def test_misfiled_derry_duplicates_are_skipped(self) -> None:
        for key in ("churchtv", "foxfordparish"):
            path = REPO_ROOT / "parishes" / "recipes" / "derry" / f"{key}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload.get("skip"), key)

    def test_clonleigh_candidates_include_sunday_publish_folder(self) -> None:
        urls = clonleigh_candidate_urls(date(2026, 10, 25))
        self.assertEqual(len(urls), 2)
        self.assertIn("/2026/10/24/", urls[0])  # Saturday legacy
        self.assertIn("/2026/10/25/", urls[1])  # Sunday proved 29/10/2026
        self.assertTrue(all("25th-october-2026" in u for u in urls))


if __name__ == "__main__":
    unittest.main()
