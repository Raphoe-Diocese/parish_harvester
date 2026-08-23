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
        by_key = {entry.key: entry for entry in parse_evidence_file("clogher_diocese", PARISHES)}
        self.assertIn("Monaghan", by_key["tyholland"].display_name)
        self.assertIn("past-newsletters", by_key["tyholland"].bulletin_page)
        self.assertIn("Clontibret", by_key["castleblayney"].display_name)

    def test_harvestable_parishes_keep_real_bulletin_urls(self) -> None:
        by_key = {entry.key: entry for entry in parse_evidence_file("clogher_diocese", PARISHES)}
        self.assertIn("[2026-8-23]", by_key["carrickmacross"].example_url)
        self.assertIn("Clontibret-Muckno-Bulletin-23rd-AUG-2026", by_key["castleblayney"].example_url)
        self.assertTrue(by_key["derrygonnelly"].example_url.endswith("23.08.2026.pdf"))
        self.assertIn("Sunday-23rd-August-2026", by_key["donaghmoyne"].example_url)
        self.assertIn("Bulletin-Sunday-23rd-August-2026", by_key["roslea"].example_url)
        self.assertIn("09.02.2025", by_key["bundoran"].example_url)
        self.assertIn("Sunday 23rd August 2026.pdf", by_key["clones"].example_url)
        self.assertIn("230826.pdf", by_key["enniskillen"].example_url)
        self.assertIn("Sunday-23rd-August-2026.jpg", by_key["fintona"].example_url)
        self.assertIn("23082026.pdf", by_key["lisnaskeamaguiresbridge"].example_url)
        self.assertIn("23082026.pdf", by_key["monaghanrackwallace"].example_url)
        self.assertIn("culmaine.co.uk/newsletter", by_key["ederney"].example_url)
        self.assertIn("donaghparish.com/parish-news", by_key["donagh"].example_url)
        self.assertIn("_files/ugd/", by_key["irvinestown"].example_url)
        self.assertIn("onewebmedia/S25C", by_key["newtownbutler"].example_url)
        self.assertIn("Newsletter-23.08.2026.pdf", by_key["corcaghanthreemilehouse"].example_url)
        self.assertIn("23rd-August-2026-.rtf", by_key["magheracloone"].example_url)
        self.assertIn("truaghparish.com", by_key["errigaltruagh"].example_url)
        self.assertIn("14th-June.jpg", by_key["dromore"].example_url)
        self.assertIn("pdf/230826.pdf", by_key["tempo"].example_url)
        self.assertIn("parishnews.htm", by_key["ballybay"].example_url)
        self.assertIn("killannyparish.ie/parish-bulletin", by_key["killanny"].example_url)
        killanny = load_recipe(recipe_path_for("killanny", PARISHES))
        self.assertFalse(_recipe_is_inactive(killanny))
        self.assertIn("parish-bulletin", killanny["start_url"])
        self.assertTrue(any(step.get("skip_listing_nav") for step in killanny.get("steps", [])))

    def test_facebook_and_link_only_recipes_are_skipped(self) -> None:
        facebook = load_recipe(recipe_path_for("aughnamulleneast", PARISHES))
        self.assertTrue(_recipe_is_inactive(facebook))
        self.assertIn("facebook.com", facebook["start_url"])
        clontibret = load_recipe(recipe_path_for("clontibret", PARISHES))
        self.assertTrue(_recipe_is_inactive(clontibret))
        self.assertIn("mucknoparish.ie", clontibret["start_url"])
        tyholland = load_recipe(recipe_path_for("tyholland", PARISHES))
        self.assertTrue(_recipe_is_inactive(tyholland))
        self.assertIn("past-newsletters", tyholland["start_url"])
        self.assertNotIn("23082026.pdf", json.dumps(tyholland))
        clones = load_recipe(recipe_path_for("clones", PARISHES))
        self.assertFalse(_recipe_is_inactive(clones))
        self.assertIn("clonesparish.com", clones["start_url"])
        self.assertNotIn("clonesparish.ie", clones["start_url"])

    def test_contacts_and_diocese_label(self) -> None:
        contacts = json.loads((PARISHES / "clogher_diocese_contacts.json").read_text(encoding="utf-8"))
        self.assertEqual(len(contacts), 37)
        self.assertEqual(contacts["ederney"]["display_name"], "Ederney (Cúl Máine)")
        self.assertEqual(
            contacts["tyholland"]["display_name"],
            "Tyholland (bulletin with Monaghan & Rackwallace)",
        )
        self.assertIn("past-newsletters", contacts["tyholland"]["website"])
        self.assertEqual(
            contacts["monaghanrackwallace"]["display_name"],
            "Monaghan & Rackwallace (includes Tyholland)",
        )
        self.assertEqual(
            contacts["clontibret"]["display_name"],
            "Clontibret (bulletin with Castleblayney / Muckno)",
        )
        self.assertEqual(_diocese_label("clogher_diocese"), "Clogher Diocese")


if __name__ == "__main__":
    unittest.main()
