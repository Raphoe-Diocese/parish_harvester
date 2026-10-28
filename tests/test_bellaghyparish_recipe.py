from __future__ import annotations

import json
import unittest
from pathlib import Path

from harvester.bulletin_freshness import suggest_retry_strategy
from harvester.fetcher import FetchResult, ParishEntry, _apply_recipe_timeouts


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "parishes" / "recipes" / "derry" / "bellaghyparish.json"
CURRENT = "https://bellaghyparish.com/current-newsletter/"


class BellaghyParishRecipeTests(unittest.TestCase):
    def test_recipe_keeps_permanent_redirect_without_homepage_rescrape(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "bellaghyparish")
        self.assertEqual(payload.get("site_type"), "permanent_redirect_document")
        self.assertEqual(payload.get("start_url"), CURRENT)
        self.assertTrue(payload.get("disable_stale_rescrape_fallback"))
        self.assertNotIn("skip", payload)

        notes = " ".join(payload.get("do_not") or []).lower()
        self.assertIn("pope", notes)
        self.assertIn("homepage", notes)

    def test_current_newsletter_stale_is_manual_review(self) -> None:
        entry = ParishEntry(
            key="bellaghyparish",
            display_name="Bellaghy",
            pattern="",
            content_type="pdf",
            example_url="https://bellaghyparish.com/wp-content/uploads/2026/10/11-October-2026.pdf",
            bulletin_page=CURRENT,
        )
        # Resolved PDF URL is dated; bulletin_page still names the permanent redirect.
        result = FetchResult(
            key="bellaghyparish",
            display_name="Bellaghy",
            status="ok",
            url="https://bellaghyparish.com/wp-content/uploads/2026/10/11-October-2026.pdf",
            file_type="pdf",
        )
        self.assertEqual(suggest_retry_strategy(result, entry), "manual_review")

    def test_recipe_ignore_https_errors_merges_into_host_profile(self) -> None:
        merged = _apply_recipe_timeouts(
            {"ignore_https_errors": False, "navigation_timeout_ms": 40_000},
            {"ignore_https_errors": True, "timeout_ms": 45_000},
        )
        self.assertTrue(merged["ignore_https_errors"])


if __name__ == "__main__":
    unittest.main()
