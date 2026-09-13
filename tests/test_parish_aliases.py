from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.fetcher import FetchResult
from harvester.parish_aliases import (
    ALIAS_TO_CANONICAL,
    DRIVE_FOLDER_LISTING_ERROR,
    HARVEST_INPUT_ALIASES,
    canonical_key,
    collapse_named_links,
    combined_display_name,
    is_alias_key,
    is_drive_folder_listing,
    reject_drive_folder_listing,
    resolve_harvest_key,
)
from ocr.generate_bulletin_pages import render_parish_link_grid

REPO_ROOT = Path(__file__).resolve().parent.parent


class ParishAliasTests(unittest.TestCase):
    def test_only_the_two_verified_aliases(self) -> None:
        self.assertEqual(
            ALIAS_TO_CANONICAL,
            {
                "ballintra": "drumholm-parish",
                "kilmacrenan": "drive-1kna8f6t54",
            },
        )

    def test_ballintra_is_drumholm(self) -> None:
        self.assertTrue(is_alias_key("ballintra"))
        self.assertEqual(canonical_key("ballintra"), "drumholm-parish")
        self.assertEqual(combined_display_name("ballintra"), "Drumholm (Ballintra)")
        self.assertEqual(combined_display_name("drumholm-parish"), "Drumholm (Ballintra)")
        self.assertFalse(is_alias_key("drumholm-parish"))

    def test_kilmacrenan_shares_gartan_termon_drive_file(self) -> None:
        gartan = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "raphoe" / "drive-1kna8f6t54.json").read_text(
                encoding="utf-8"
            )
        )
        kilmac = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "raphoe" / "kilmacrenan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("1KnA8F6t54", gartan.get("start_url", ""))
        self.assertIn("1KnA8F6t54", kilmac.get("start_url", ""))
        self.assertEqual(kilmac.get("alias_of"), "drive-1kna8f6t54")
        self.assertEqual(canonical_key("kilmacrenan"), "drive-1kna8f6t54")
        self.assertEqual(
            combined_display_name("drive-1kna8f6t54"),
            "Gartan/Termon (Kilmacrenan)",
        )

    def test_collapse_drops_duplicate_ballintra_row(self) -> None:
        collapsed = collapse_named_links(
            [
                ("Ballintra Parish", "https://www.facebook.com/donalquinn1959"),
                (
                    "Drumholm",
                    "https://www.parishpress.net/wp-content/uploads/parish-bulletins/donegal/raphoe/drumholm-parish/bulletin.pdf",
                ),
                ("Ardara", "http://ardara.ie/news/"),
            ]
        )
        names = [name for name, _url in collapsed]
        self.assertEqual(names.count("Drumholm (Ballintra)"), 1)
        self.assertNotIn("Ballintra Parish", names)
        self.assertIn("Ardara", names)
        drumholm_url = dict(collapsed)["Drumholm (Ballintra)"]
        self.assertIn("drumholm-parish/bulletin.pdf", drumholm_url)
        self.assertNotIn("facebook.com", drumholm_url)

    def test_grid_uses_one_drumholm_ballintra_name(self) -> None:
        html = render_parish_link_grid(
            [
                ("Ballintra Parish", "https://www.facebook.com/donalquinn1959"),
                (
                    "Drumholm",
                    "https://www.parishpress.net/wp-content/uploads/parish-bulletins/donegal/raphoe/drumholm-parish/bulletin.pdf",
                ),
            ]
        )
        self.assertIn("Drumholm (Ballintra)", html)
        self.assertNotIn("Ballintra Parish", html)
        self.assertEqual(html.count("parish-item"), 1)

    def test_recipes_keep_drumholm_pdf_and_mark_ballintra_alias(self) -> None:
        ballintra = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "raphoe" / "ballintra.json").read_text(
                encoding="utf-8"
            )
        )
        drumholm = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "raphoe" / "drumholm-parish.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(ballintra.get("alias_of"), "drumholm-parish")
        self.assertTrue(ballintra.get("skip"))
        self.assertIn("drumholm-parish/bulletin.pdf", drumholm.get("start_url", ""))
        self.assertNotEqual(drumholm.get("skip"), True)

    def test_bruckless_harvest_input_is_not_a_skip_alias(self) -> None:
        self.assertEqual(HARVEST_INPUT_ALIASES["bruckless"], "drive-1rjeey-ayy")
        self.assertNotIn("bruckless", ALIAS_TO_CANONICAL)
        self.assertEqual(resolve_harvest_key("bruckless"), "drive-1rjeey-ayy")
        self.assertEqual(resolve_harvest_key("Bruckless"), "drive-1rjeey-ayy")
        self.assertEqual(resolve_harvest_key("drive-1rjeey-ayy"), "drive-1rjeey-ayy")
        self.assertEqual(resolve_harvest_key("ballintra"), "ballintra")
        recipe = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "raphoe" / "drive-1rjeey-ayy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(recipe.get("display_name"), "Bruckless")
        self.assertFalse(recipe.get("skip"))

    def test_drive_folder_listing_never_stays_ok(self) -> None:
        folder = "https://drive.google.com/drive/folders/1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK"
        file_url = "https://drive.usercontent.google.com/download?id=1fiUdWkLFOaVNqaStLuM6Doqynx59_ss-&export=download"
        self.assertTrue(is_drive_folder_listing(folder))
        self.assertFalse(is_drive_folder_listing(file_url))
        self.assertFalse(
            is_drive_folder_listing("https://drive.google.com/file/d/1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa/view")
        )
        bad = reject_drive_folder_listing(
            FetchResult(key="drive-1rjeey-ayy", display_name="Bruckless", status="ok", url=folder)
        )
        self.assertEqual(bad.status, "error")
        self.assertEqual(bad.error, DRIVE_FOLDER_LISTING_ERROR)
        good = reject_drive_folder_listing(
            FetchResult(key="drive-1rjeey-ayy", display_name="Bruckless", status="ok", url=file_url)
        )
        self.assertEqual(good.status, "ok")
        self.assertEqual(good.error, "")


if __name__ == "__main__":
    unittest.main()
