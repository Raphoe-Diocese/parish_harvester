from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.replay import _apply_recipe_host_overrides


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "parishes" / "recipes" / "derry" / "clonmanyparish.json"
PDF = "https://clonmanyparish.com/pdf/251026.pdf"


class ClonmanyParishRecipeTests(unittest.TestCase):
    def test_recipe_uses_com_dated_pdf_not_ie_listing(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "clonmanyparish")
        self.assertEqual(payload.get("site_type"), "dated_pdf_path")
        self.assertEqual(payload.get("start_url"), PDF)
        self.assertEqual(payload.get("example_url"), PDF)
        self.assertTrue(payload.get("ignore_https_errors"))
        self.assertNotIn("clonmanyparish.ie/newsletter", json.dumps(payload))
        self.assertNotIn("2026-06-28", json.dumps(payload))

        steps = payload.get("steps") or []
        self.assertEqual(steps[0].get("action"), "download")
        self.assertEqual(steps[0].get("url"), PDF)

        merged = _apply_recipe_host_overrides(
            {"ignore_https_errors": False},
            payload,
        )
        self.assertTrue(merged["ignore_https_errors"])


if __name__ == "__main__":
    unittest.main()
