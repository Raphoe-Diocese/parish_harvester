from __future__ import annotations

import os
import unittest
from pathlib import Path

import harvester.fetcher as fetcher


class HostProfilesTests(unittest.TestCase):
    def setUp(self) -> None:
        fetcher._HOST_PROFILES_CACHE = None

    def test_get_host_profile_returns_override_for_listed_host(self) -> None:
        profile = fetcher._get_host_profile("https://ballyclareballygowan.com/notice%20board.htm")

        self.assertEqual(profile["navigation_timeout_ms"], 60000)
        self.assertEqual(profile["max_retries"], 3)

    def test_get_host_profile_threepatrons_has_long_timeout(self) -> None:
        profile = fetcher._get_host_profile("https://www.threepatrons.org/")

        self.assertEqual(profile["navigation_timeout_ms"], 60000)
        self.assertEqual(profile["total_timeout_s"], 120)
        self.assertTrue(profile["prefer_headful"])

    def test_recipe_uses_trained_click_download(self) -> None:
        recipe = {
            "playbook_type": "weekly_bulletin_download",
            "steps": [{"action": "goto", "url": "https://threepatrons.org/"}],
        }
        self.assertTrue(fetcher._recipe_uses_trained_click_download(recipe))

        click_recipe = {
            "steps": [
                {"action": "goto", "url": "https://example.org/"},
                {"action": "click", "selector": "a"},
            ]
        }
        self.assertTrue(fetcher._recipe_uses_trained_click_download(click_recipe))
        self.assertFalse(fetcher._recipe_uses_trained_click_download({"steps": [{"action": "download"}]}))

    def test_trained_recipe_disables_legacy_fallbacks(self) -> None:
        recipe_path = Path("/tmp/example.json")
        recipe_meta = {"steps": [{"action": "goto", "url": "https://example.org/"}]}
        self.assertTrue(fetcher._trained_recipe_exists(recipe_path, recipe_meta))
        self.assertFalse(fetcher._legacy_fallbacks_enabled(recipe_path, recipe_meta))

    def test_mistral_fallback_disabled_for_trained_recipes(self) -> None:
        recipe_path = Path("/tmp/example.json")
        recipe_meta = {"steps": [{"action": "click", "selector": "a"}]}
        with unittest.mock.patch.dict(os.environ, {"PARISH_MISTRAL_FALLBACK": "1", "MISTRAL_API_KEY": "x"}):
            self.assertFalse(fetcher._mistral_fallback_enabled(recipe_path, recipe_meta))

    def test_get_host_profile_returns_defaults_for_unlisted_host(self) -> None:
        profile = fetcher._get_host_profile("https://example.org/bulletins")

        self.assertEqual(profile["navigation_timeout_ms"], 30000)
        self.assertEqual(profile["max_retries"], 2)
        self.assertEqual(profile["retry_backoff_ms"], 2000)


if __name__ == "__main__":
    unittest.main()
