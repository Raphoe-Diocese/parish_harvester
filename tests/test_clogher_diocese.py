from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.fetcher import parse_evidence_file
from harvester.parish_status import _diocese_label
from harvester.report import _recipe_is_inactive
from harvester.replay import load_recipe, recipe_path_for

REPO = Path(__file__).resolve().parent.parent
PARISHES = REPO / "parishes"


class ClogherDioceseTests(unittest.TestCase):
    def test_evidence_has_unique_keys_for_every_official_parish(self) -> None:
        entries = parse_evidence_file("clogher_diocese", PARISHES)
        keys = [entry.key for entry in entries]
        self.assertEqual(len(keys), 37)
        self.assertEqual(len(set(keys)), 37)
        self.assertIn("clogherparish", keys)
        self.assertNotIn("clogher", keys)

    def test_harvestable_parishes_keep_real_bulletin_urls(self) -> None:
        by_key = {entry.key: entry for entry in parse_evidence_file("clogher_diocese", PARISHES)}
        self.assertIn("[2026-8-23]", by_key["carrickmacross"].example_url)
        self.assertIn("Clontibret-Muckno-Bulletin-23rd-AUG-2026", by_key["castleblayney"].example_url)
        self.assertTrue(by_key["derrygonnelly"].example_url.endswith("23.08.2026.pdf"))
        self.assertIn("Sunday-23rd-August-2026", by_key["donaghmoyne"].example_url)
        self.assertIn("Bulletin-Sunday-23rd-August-2026", by_key["roslea"].example_url)
        self.assertIn("09.02.2025", by_key["bundoran"].example_url)

    def test_facebook_and_link_only_recipes_are_skipped(self) -> None:
        facebook = load_recipe(recipe_path_for("aughnamulleneast", PARISHES))
        self.assertTrue(_recipe_is_inactive(facebook))
        self.assertIn("facebook.com", facebook["start_url"])
        clontibret = load_recipe(recipe_path_for("clontibret", PARISHES))
        self.assertTrue(_recipe_is_inactive(clontibret))
        self.assertIn("mucknoparish.ie", clontibret["start_url"])

    def test_contacts_and_diocese_label(self) -> None:
        contacts = json.loads((PARISHES / "clogher_diocese_contacts.json").read_text(encoding="utf-8"))
        self.assertEqual(len(contacts), 37)
        self.assertEqual(contacts["ederney"]["display_name"], "Ederney (Cúl Máine)")
        self.assertEqual(_diocese_label("clogher_diocese"), "Clogher Diocese")


if __name__ == "__main__":
    unittest.main()
