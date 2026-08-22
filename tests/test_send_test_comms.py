"""Send & test must talk to GitHub and stop on a real result or a clear error."""
from __future__ import annotations

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
PUSH_JS = REPO / "extension" / "github_recipe_push.js"
CONTENT_JS = REPO / "extension" / "content.js"
HARVEST_YML = REPO / ".github" / "workflows" / "harvest.yml"
MANIFEST = REPO / "extension" / "manifest.json"


class SendTestCommsTests(unittest.TestCase):
    def test_failed_dispatch_is_not_treated_as_pending(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn("dispatchPending: false", content)
        self.assertNotIn("dispatchPending: !dispatchResult.ok", content)

    def test_dispatch_explains_404(self) -> None:
        push = PUSH_JS.read_text(encoding="utf-8")
        self.assertIn("GitHub could not start harvest.yml (404)", push)
        self.assertIn("harvest.yml/dispatches", push)

    def test_poll_finishes_on_fresh_parish_status(self) -> None:
        push = PUSH_JS.read_text(encoding="utf-8")
        self.assertIn("function isFreshHarvestTimestamp", push)
        self.assertIn("function outcomeFromFreshStatus", push)
        self.assertIn("SEND_TEST_MAX_WAIT_MS", push)
        self.assertIn("15 * 60 * 1000", push)
        self.assertIn("no_actions_read", push)
        self.assertIn("cancelled", push)
        self.assertIn("harvestRunMatchesParish", push)

    def test_harvest_run_name_and_single_parish_queue(self) -> None:
        yml = HARVEST_YML.read_text(encoding="utf-8")
        self.assertIn("run-name: Harvest ${{ inputs.target_parish || 'full' }}", yml)
        self.assertIn("harvest-${{ github.event.inputs.target_parish || 'full' }}", yml)
        self.assertIn(
            "if: github.event_name != 'workflow_dispatch' || github.event.inputs.target_parish == ''",
            yml,
        )
        self.assertIn("Cache Playwright browsers", yml)

    def test_manifest_bumped_for_extension_js(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('"version": "1.61.15"', text)

    def test_back_room_fetches_fresh_parish_status(self) -> None:
        push = PUSH_JS.read_text(encoding="utf-8")
        sidepanel = (REPO / "extension" / "sidepanel.js").read_text(encoding="utf-8")
        html = (REPO / "extension" / "sidepanel.html").read_text(encoding="utf-8")
        self.assertIn("const fetchLatestFileCommit", push)
        self.assertIn("parishes/parish_status.json", push)
        self.assertIn("cache: \"no-store\"", push)
        self.assertIn("attachStatusFetchMeta", push)
        self.assertNotIn("ph_parish_status_cache", sidepanel)
        self.assertIn("function formatUkDateTime", sidepanel)
        self.assertIn("function _problemsSetRefreshedLine", sidepanel)
        self.assertIn("message.dispatch_at", sidepanel)
        self.assertIn("2 * 60 * 1000", sidepanel)
        self.assertIn("id=\"problems-refreshed\"", html)
        self.assertIn("id=\"problems-refresh-btn\"", html)

    def test_harvest_commits_parish_status_after_single_parish(self) -> None:
        yml = HARVEST_YML.read_text(encoding="utf-8")
        self.assertIn("if: steps.harvest_run.outcome == 'success'", yml)
        self.assertIn("parishes/parish_status.json", yml)
        self.assertIn("Partial harvests are normal", yml)
        self.assertIn("git commit -m", yml)
        self.assertIn('Including proof PDF: Bulletins/${TARGET_PARISH}.pdf', yml)
        self.assertIn("all_bulletins_*)", yml)
        self.assertNotIn("zip old", yml.lower())

    def test_ballinascreen_uses_wix_predictor_then_image_stack(self) -> None:
        recipe = (
            REPO / "parishes" / "recipes" / "derry" / "parishofballinascreen.json"
        ).read_text(encoding="utf-8")
        self.assertIn("wix_dated_slug", recipe)
        self.assertIn("image_stack", recipe)
        self.assertNotIn('"action": "print_to_pdf"', recipe)

    def test_stteresas_uses_wp_json_post_images(self) -> None:
        recipe = (
            REPO / "parishes" / "recipes" / "down_and_connor" / "stteresasparish.json"
        ).read_text(encoding="utf-8")
        self.assertIn("wp_json_newest_post_images", recipe)
        self.assertIn("the-st-teresas-parish-bulletin-for-sunday", recipe)
        self.assertIn("image_stack", recipe)
        self.assertIn('"count": 2', recipe)
        self.assertNotIn('"action": "print_to_pdf"', recipe)


if __name__ == "__main__":
    unittest.main()
