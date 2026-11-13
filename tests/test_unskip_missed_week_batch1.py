"""Step 4 batch 1: first 25 missed-week recipes are active again."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.report import _recipe_is_inactive

KEYS = [
    "bessbrook",
    "coagh",
    "crossmaglen",
    "dromintee",
    "drumcree",
    "dundalkstpatricks",
    "dungannon",
    "eglish",
    "faughart",
    "keadyderrynooseandmadden",
    "kilmore",
    "lordship",
    "magherafelt",
    "middletown",
    "pomeroy",
    "togher",
    "anacartydonohill",
    "ballinaboher",
    "ballinahinchkilloscully",
    "ballingarry",
    "ballybrickenbohermore",
    "ballylanders",
    "banshakilmoyler",
    "boherlahandualla",
    "borrisoleighileigh",
]


class UnskipMissedWeekBatch1Tests(unittest.TestCase):
    def test_batch_is_active_and_runnable(self) -> None:
        root = Path("parishes/recipes")
        by_key: dict[str, Path] = {}
        for path in root.glob("*/*.json"):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            key = str(data.get("parish_key") or path.stem)
            if key in KEYS:
                by_key[key] = path
        self.assertEqual(sorted(by_key), sorted(KEYS))
        for key, path in by_key.items():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertFalse(data.get("skip"), key)
            self.assertEqual(data.get("status"), "active", key)
            self.assertFalse(_recipe_is_inactive(data), key)


if __name__ == "__main__":
    unittest.main()
