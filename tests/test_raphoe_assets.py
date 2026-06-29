from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class RaphoeAssetsTests(unittest.TestCase):
    def test_renamed_raphoe_evidence_file_is_structured(self) -> None:
        evidence_path = REPO_ROOT / "parishes" / "raphoe_diocese_bulletin_urls.txt"
        old_path = REPO_ROOT / "parishes" / "raphoe diocese urls.txt"

        text = evidence_path.read_text(encoding="utf-8")
        self.assertTrue(evidence_path.exists())
        self.assertFalse(old_path.exists())
        self.assertIn("# --- Ardara ---", text)
        self.assertIn("# --- Cathedral ---", text)
        self.assertIn("# --- Templecrone ---", text)
        self.assertIn("# --- Raphoe ---", text)
        self.assertIn("drive.usercontent.google.com/download?id=1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa&export=download", text)
        self.assertEqual(text.count("milfordrathmullanparishes.ie/bulletins/"), 4)

    def test_raphoe_contacts_file_contains_placeholder_entries(self) -> None:
        contacts_path = REPO_ROOT / "parishes" / "raphoe_diocese_contacts.json"
        payload = json.loads(contacts_path.read_text(encoding="utf-8"))

        self.assertIn("ardara", payload)
        self.assertIn("drive-1jmslbrliw", payload)
        self.assertIn("drive-1hh7w-ew0v", payload)
        self.assertEqual(payload["drive-1hh7w-ew0v"]["display_name"], "Templecrone")
        self.assertEqual(
            payload["drive-1hh7w-ew0v"]["website"],
            "https://drive.google.com/file/d/1Hh7w-Ew0vLJUFMihFiVzVJGhjeYposIH/view",
        )
        self.assertEqual(payload["steunanscathedral"]["display_name"], "Cathedral")


    def test_raphoe_bruckless_recipe_uses_cloud_folder(self) -> None:
        recipe_path = REPO_ROOT / "parishes" / "recipes" / "raphoe" / "drive-1rjeey-ayy.json"
        payload = json.loads(recipe_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("site_type"), "cloud_folder")
        self.assertNotIn("skip", payload)
        self.assertIn("1z9goh6DrkCUkpJMDbwfsi28Yc_t0_ltC", payload.get("start_url", ""))


if __name__ == "__main__":
    unittest.main()
