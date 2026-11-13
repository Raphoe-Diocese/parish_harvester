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
        found = 0
        for path in root.glob("*/*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            key = str(data.get("parish_key") or path.stem)
            if key not in KEYS:
                continue
            found += 1
            self.assertFalse(data.get("skip"), key)
            self.assertEqual(data.get("status"), "active", key)
            self.assertFalse(_recipe_is_inactive(data), key)
        self.assertEqual(found, len(KEYS))


if __name__ == "__main__":
    unittest.main()
