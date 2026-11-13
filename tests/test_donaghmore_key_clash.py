"""Dromore Donaghmore must win over the Armagh Facebook-only skip."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.replay import recipe_path_for

REPO = Path(__file__).resolve().parent.parent
PARISHES = REPO / "parishes"


class DonaghmoreKeyClashTests(unittest.TestCase):
    def test_recipe_path_prefers_active_dromore_donaghmore(self) -> None:
        path = recipe_path_for("donaghmore", PARISHES)
        self.assertEqual(path.name, "donaghmore.json")
        self.assertEqual(path.parent.name, "dromore")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertFalse(data.get("skip"))
        self.assertEqual(data.get("status"), "active")
        self.assertIn("donaghmoreparish.org", data.get("start_url", ""))

    def test_armagh_facebook_skip_has_its_own_key(self) -> None:
        armagh = PARISHES / "recipes" / "armagh" / "donaghmorearmagh.json"
        self.assertTrue(armagh.exists())
        self.assertFalse((PARISHES / "recipes" / "armagh" / "donaghmore.json").exists())
        data = json.loads(armagh.read_text(encoding="utf-8-sig"))
        self.assertEqual(data.get("parish_key"), "donaghmorearmagh")
        self.assertTrue(data.get("skip"))


if __name__ == "__main__":
    unittest.main()
