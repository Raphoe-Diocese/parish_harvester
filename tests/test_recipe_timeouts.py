from __future__ import annotations

import unittest

from harvester.fetcher import _apply_recipe_timeouts, _timeout_diagnosis


class RecipeTimeoutTests(unittest.TestCase):
    def test_timeout_field_derives_total_budget_not_60s_default(self) -> None:
        profile = {"navigation_timeout_ms": 45_000, "total_timeout_s": 60}
        recipe = {
            "timeout": 60_000,
            "steps": [{"action": "goto"}, {"action": "click"}, {"action": "download"}],
        }
        merged = _apply_recipe_timeouts(profile, recipe)
        self.assertEqual(merged["navigation_timeout_ms"], 60_000)
        self.assertGreaterEqual(merged["total_timeout_s"], 120)
        self.assertLessEqual(merged["total_timeout_s"], 600)

    def test_observed_load_ms_still_wins_when_present(self) -> None:
        profile = {"navigation_timeout_ms": 45_000, "total_timeout_s": 60}
        recipe = {
            "observed_load_ms": 90_000,
            "steps": [{"action": "goto"}, {"action": "image_stack"}],
        }
        merged = _apply_recipe_timeouts(profile, recipe)
        self.assertEqual(merged["navigation_timeout_ms"], 180_000)
        self.assertGreaterEqual(merged["total_timeout_s"], 90)

    def test_diagnosis_includes_budget_fields(self) -> None:
        recipe = {"timeout": 30_000, "steps": [{"action": "goto"}, {"action": "print_to_pdf"}]}
        profile = _apply_recipe_timeouts({}, recipe)
        diag = _timeout_diagnosis(recipe, profile)
        self.assertEqual(diag["step_count"], 2)
        self.assertEqual(diag["recipe_timeout_ms"], 30_000)
        self.assertGreaterEqual(diag["total_timeout_s"], 120)


if __name__ == "__main__":
    unittest.main()
