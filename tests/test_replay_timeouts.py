from __future__ import annotations

import unittest

from harvester.replay import (
    _recipe_navigation_wait_until,
    _recipe_start_url,
    _recipe_step_timeout_ms,
)


class ReplayTimeoutTests(unittest.TestCase):
    def test_start_url_from_goto_step(self) -> None:
        recipe = {
            "steps": [{"action": "goto", "url": "https://www.antrimparish.com/bulletinpage/"}]
        }
        self.assertEqual(
            _recipe_start_url(recipe),
            "https://www.antrimparish.com/bulletinpage/",
        )

    def test_antrim_recipe_uses_host_profile_timeout_and_commit(self) -> None:
        recipe = {
            "start_url": "https://www.antrimparish.com/bulletinpage/",
            "steps": [
                {"action": "goto", "url": "https://www.antrimparish.com/bulletinpage/"},
                {"action": "download", "url_pattern": "*.pdf"},
            ],
        }
        self.assertGreaterEqual(_recipe_step_timeout_ms(recipe), 60_000)
        self.assertEqual(_recipe_navigation_wait_until(recipe), "commit")

    def test_recipe_explicit_navigation_overrides_host(self) -> None:
        recipe = {
            "start_url": "https://www.antrimparish.com/bulletinpage/",
            "navigation_wait_until": "load",
            "steps": [{"action": "goto", "url": "https://www.antrimparish.com/bulletinpage/"}],
        }
        self.assertEqual(_recipe_navigation_wait_until(recipe), "load")

    def test_recipe_timeout_ms_respected(self) -> None:
        recipe = {
            "start_url": "https://example.com/",
            "timeout_ms": 90_000,
            "steps": [{"action": "goto", "url": "https://example.com/"}],
        }
        self.assertEqual(_recipe_step_timeout_ms(recipe), 90_000)


if __name__ == "__main__":
    unittest.main()
