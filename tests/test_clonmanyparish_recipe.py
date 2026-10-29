from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.replay import _apply_recipe_host_overrides


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "parishes" / "recipes" / "derry" / "clonmanyparish.json"


class ClonmanyParishRecipeTests(unittest.TestCase):
    def test_recipe_ignores_https_errors_for_bad_cert(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "clonmanyparish")
        self.assertTrue(payload.get("ignore_https_errors"))
        self.assertEqual(
            payload.get("start_url"),
            "https://clonmanyparish.ie/newsletter/",
        )

        merged = _apply_recipe_host_overrides(
            {"ignore_https_errors": False},
            payload,
        )
        self.assertTrue(merged["ignore_https_errors"])


if __name__ == "__main__":
    unittest.main()
