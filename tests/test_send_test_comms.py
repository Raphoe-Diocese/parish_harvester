"""Send & test must talk to GitHub and stop on a real result or a clear error."""
from __future__ import annotations

import json
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
        self.assertIn("max-parallel: 4", yml)
        self.assertIn("HARVEST_SKIP_STATUS", yml)
        self.assertIn("merge_diocese_harvests.py", yml)
        stitch = yml.split("\n  stitch:", 1)[-1]
        self.assertNotIn("python -m pytest", stitch)

    def test_manifest_bumped_for_extension_js(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('"version": "1.61.42"', text)
        content = (REPO / "extension" / "content.js").read_text(encoding="utf-8")
        self.assertIn("T6: a dated bulletin page is this week's post", content)
        self.assertIn("await _setToolbarHiddenForHost(false);", content)
        kit = (REPO / "extension" / "recipe_diag_kit.js").read_text(encoding="utf-8")
        self.assertIn("pageLooksDated", kit)
        self.assertIn("HTTP_ENGINE_SITE_TYPES", kit)
        self.assertIn("Do this:", kit)
        self.assertIn("T7: 0 saved steps is normal before Yes", kit)
        self.assertIn("Noted — refresh Problems to check GitHub", content)
        self.assertNotIn("you confirmed the PDF. Recorded on GitHub", content)
        self.assertNotIn("Mark as Dead Website", content)

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

    def test_problems_console_queue_labels(self) -> None:
        html = (REPO / "extension" / "sidepanel.html").read_text(encoding="utf-8")
        sidepanel = (REPO / "extension" / "sidepanel.js").read_text(encoding="utf-8")
        self.assertIn(">Problems<", html)
        self.assertNotIn("Back room", html)
        self.assertIn("How to fix a parish (3 steps)", html)
        self.assertIn("<li><strong>Open site</strong>", html)
        self.assertIn("<li><strong>Refresh</strong>", html)
        howto = html.find('id="problems-howto"')
        harvest = html.find('id="problems-full-harvest-btn"')
        warning = html.find('id="problems-warning"')
        refresh = html.find('id="problems-refresh-btn"')
        self.assertTrue(0 <= howto < harvest < warning < refresh)
        self.assertEqual(
            html.count("<li>", howto, html.find("Need every parish again?")),
            3,
        )
        self.assertIn("Start here", sidepanel)
        self.assertIn("problems-card-next", sidepanel)
        self.assertIn("actionable_keys", sidepanel)
        self.assertIn("problems-card-advice", sidepanel)
        self.assertIn("row.advice", sidepanel)
        self.assertIn("${d}/${m}/${y}", sidepanel)

    def test_send_test_uses_saved_recipe_when_local_steps_incomplete(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn("const _recipeStepsAreComplete", content)
        self.assertIn("const _mergeWafExamplePostUrl", content)
        self.assertIn("const _urlLooksLikeOpenablePage", content)
        self.assertIn("Open — bulletin is a picture", content)
        self.assertIn("Open — bulletin is HTML (text)", content)
        self.assertIn("Open — bulletin is a PDF", content)
        self.assertIn("Mark as picture on this page", content)
        self.assertIn("Mark as HTML on this page", content)
        self.assertIn("Mark as PDF on this page", content)
        self.assertIn("awaitMarkKind", content)
        self.assertIn("openPageUrl", content)
        self.assertIn("this week's page saved", content)
        self.assertNotIn("No new tab.", content)
        self.assertIn("const _githubRecipeIsHarvestReady", content)
        self.assertIn("This week's post is on GitHub", content)
        self.assertIn("Using the saved recipe — testing this parish only. No re-train.", content)
        self.assertIn("This does not overwrite the recipe.", content)
        self.assertIn("tap Send & test to run the saved recipe.", content)
        self.assertIn("dataentry|parishioner|", content)
        self.assertIn("dispatchHarvestTest", content)

    def test_harvest_commits_parish_status_after_single_parish(self) -> None:
        yml = HARVEST_YML.read_text(encoding="utf-8")
        self.assertIn("if: steps.harvest_run.outcome == 'success'", yml)
        self.assertIn("parishes/parish_status.json", yml)
        self.assertIn("Partial harvests are normal", yml)
        self.assertIn("git commit -m", yml)
        self.assertIn("S2: do not commit PDFs", yml)
        self.assertNotIn("zip old", yml.lower())

    def test_ballinascreen_uses_wix_predictor_then_print_to_pdf(self) -> None:
        recipe = json.loads(
            (REPO / "parishes" / "recipes" / "derry" / "parishofballinascreen.json").read_text(
                encoding="utf-8"
            )
        )
        actions = [step.get("action") for step in recipe.get("steps") or []]
        self.assertEqual(recipe.get("playbook_type"), "wix_dated_slug")
        self.assertIn("print_to_pdf", actions)
        self.assertNotIn("image_stack", actions)
        print_step = next(
            step for step in recipe["steps"] if step.get("action") == "print_to_pdf"
        )
        self.assertTrue(print_step.get("skip_listing_nav"))

    def test_stteresas_uses_wp_json_post_images(self) -> None:
        recipe = (
            REPO / "parishes" / "recipes" / "down_and_connor" / "stteresasparish.json"
        ).read_text(encoding="utf-8")
        self.assertIn("wp_json_newest_post_images", recipe)
        self.assertIn("the-st-teresas-parish-bulletin-for-sunday", recipe)
        self.assertIn("image_stack", recipe)
        self.assertIn('"count": 2', recipe)
        self.assertNotIn('"action": "print_to_pdf"', recipe)

    def test_c3_rate_limit_one_poller_locate_errors(self) -> None:
        push = PUSH_JS.read_text(encoding="utf-8")
        content = CONTENT_JS.read_text(encoding="utf-8")
        sidepanel = (REPO / "extension" / "sidepanel.js").read_text(encoding="utf-8")
        self.assertIn("GitHub rate limit — try again in", push)
        self.assertIn("X-RateLimit-Remaining", push)
        self.assertIn("githubRateLimitMessage", push)
        self.assertIn("if (hard) throw hard.err;", push)
        self.assertIn('return { ok: false, error: String(err?.message || err) };', push)
        self.assertNotIn("dispatch_at: dispatchAt", content)
        self.assertIn("Math.abs(Number(stored.at) - at) < 8000", sidepanel)

    def test_c4_dead_extension_symbols_removed(self) -> None:
        bg = (REPO / "extension" / "background.js").read_text(encoding="utf-8")
        sidepanel = (REPO / "extension" / "sidepanel.js").read_text(encoding="utf-8")
        content = CONTENT_JS.read_text(encoding="utf-8")
        for needle in (
            "fetch_github_file",
            "lookup_parish_for_url",
            "recording_tab_inactive",
            "_locateRecipeOnGithub",
        ):
            self.assertNotIn(needle, bg)
        for needle in (
            "_problemsFilterActionableRows",
            "_problemsParishHarvestStatus",
            "_problemsFindLatestWorkflowRun",
            "_problemsMegaPdfForParish",
            "_problemsGithubBlobTabUrl",
            "_pdLoadHarvestReport",
        ):
            self.assertNotIn(needle, sidepanel)
        self.assertNotIn('recipe.site_type === "parish_messenger"', content)
        self.assertIn("actionable_keys", sidepanel)


if __name__ == "__main__":
    unittest.main()
