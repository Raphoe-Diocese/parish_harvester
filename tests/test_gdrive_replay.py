from __future__ import annotations

import unittest

from harvester.replay import (
    _gdrive_download_url_from_recipe,
    _goto_or_download,
    _is_gdrive_usercontent_url,
    _recipe_is_gdrive_static,
    _try_download_page_url,
)


class GdriveReplayTests(unittest.TestCase):
    def test_detects_usercontent_url(self) -> None:
        url = (
            "https://drive.usercontent.google.com/download?"
            "id=1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5&export=download"
        )
        self.assertTrue(_is_gdrive_usercontent_url(url))

    def test_recipe_is_gdrive_static_from_step_url(self) -> None:
        recipe = {
            "start_url": "https://drive.google.com/file/d/ABC/view",
            "steps": [
                {
                    "action": "download",
                    "url": "https://drive.usercontent.google.com/download?id=ABC&export=download",
                }
            ],
        }
        self.assertTrue(_recipe_is_gdrive_static(recipe))
        self.assertEqual(
            _gdrive_download_url_from_recipe(recipe),
            "https://drive.usercontent.google.com/download?id=ABC&export=download",
        )

    def test_legacy_recipe_with_usercontent_start_url(self) -> None:
        recipe = {
            "start_url": "https://drive.usercontent.google.com/download?id=OLD&export=download",
            "steps": [
                {
                    "action": "download",
                    "url": "https://drive.usercontent.google.com/download?id=OLD&export=download",
                    "use_captured_url": True,
                }
            ],
        }
        self.assertTrue(_recipe_is_gdrive_static(recipe))

    def test_gdrive_helpers_are_importable(self) -> None:
        self.assertTrue(callable(_goto_or_download))
        self.assertTrue(callable(_try_download_page_url))


if __name__ == "__main__":
    unittest.main()
