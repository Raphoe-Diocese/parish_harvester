from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_JS = REPO_ROOT / "extension" / "content.js"
SIDEPANEL_JS = REPO_ROOT / "extension" / "sidepanel.js"
POPUP_HTML = REPO_ROOT / "extension" / "popup.html"
POPUP_JS = REPO_ROOT / "extension" / "popup.js"
SIDEPANEL_HTML = REPO_ROOT / "extension" / "sidepanel.html"
MANIFEST_JSON = REPO_ROOT / "extension" / "manifest.json"


class ExtensionMessagingTests(unittest.TestCase):
    def test_mark_image_returns_explicit_failure_reasons(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn('if (!imageUrl)', content)
        self.assertIn('reason: "No image URL was provided."', content)
        self.assertIn('unavailableReason: "Image mark handler is unavailable on this page."', content)

    def test_recipe_steps_are_single_source_of_truth(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn("let recipeSteps = [];", content)
        self.assertIn("const _standaloneRecipeSteps = () =>", content)
        self.assertIn("if (_standaloneRecipeSteps().length === 0)", content)
        self.assertNotIn("let sessionSteps = []", content)
        self.assertNotIn("const standaloneSteps = []", content)

    def test_sidepanel_uses_reason_for_error_status(self) -> None:
        sidepanel = SIDEPANEL_JS.read_text(encoding="utf-8")
        self.assertIn('setStatus(`❌ ${result?.reason || _dispatchErrorText(result)}`, "err")', sidepanel)
        self.assertIn("statusEl.dataset.status", sidepanel)

    def test_problems_back_room_uses_parish_status_cards(self) -> None:
        html = SIDEPANEL_HTML.read_text(encoding="utf-8")
        js = SIDEPANEL_JS.read_text(encoding="utf-8")
        self.assertIn('id="problems-cards"', html)
        self.assertIn('id="drive-trainer-warning"', html)
        self.assertIn("Save this PDF", html)
        self.assertIn("More actions", html)
        self.assertIn("Open site", js)
        self.assertIn("View bulletin", js)
        self.assertIn("_problemsOpenHarvestedPdf", js)
        self.assertIn("_problemsHarvestPdfCandidates", js)
        self.assertIn("Bulletins/${key}.pdf", js)
        self.assertIn("parishpress.ie/parishes", js)
        self.assertIn('Range: "bytes=0-7"', js)
        self.assertIn("_problemsUrlLooksLikeZip", js)
        self.assertIn("Send & test", js)
        self.assertIn("_problemsRowsFromStatus", js)
        self.assertIn("actionable_keys", js)
        self.assertIn("formatUkDate", js)
        self.assertIn("_problemsBulletinDateFromStatus", js)
        self.assertIn("_problemsPlainStatus", js)
        self.assertIn('PROBLEMS_DEFAULT_DIOCESE = "Raphoe Diocese"', js)
        self.assertIn('PROBLEMS_FIX_VISITED_KEY = "ph_problems_fix_visited"', js)
        self.assertIn("ph_problems_ui", js)
        self.assertNotIn("problems-body", html)
        self.assertNotIn("parish_health", js)

    def test_trainer_send_and_test_hook_and_drive_warning(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn('id = "ph-send-and-test-btn"', content)
        self.assertIn('message.type === "ph_send_and_test"', content)
        self.assertIn("Do not use ⋮ More actions", content)
        self.assertIn("Save this PDF", content)

    def test_mark_image_standalone_path_uses_single_recipe_step_append(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        marker = 'const recipeStep = useStack\n            ? { action: "image_stack", count: urls.length, urls }\n            : { action: "image", url: urls[0] };'
        self.assertIn(marker, content)
        block_start = content.index(marker)
        block_end = content.index("pickedImages = [];", block_start)
        self.assertIn("standaloneAddStep(", content[block_start:block_end])

    def test_toolbar_core_controls_and_advanced_fold_exist(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        for label in (
            "📄 Get a PDF",
            "🔗 1. Follow a link",
            "🖼️ Pick bulletin image on this page",
            "📐 It's in a frame / viewer",
            "🔍 Find bulletin on this page",
            "📋 Recipe Preview",
            "⬆ Push Recipe to GitHub",
            "ph_recording_session",
        ):
            self.assertIn(label, content)
        self.assertIn('document.createElement("details")', content)
        self.assertIn('advancedSummary.textContent = "▾ Advanced";', content)

    def test_settings_hooks_exist(self) -> None:
        popup_html = POPUP_HTML.read_text(encoding="utf-8")
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        manifest_json = MANIFEST_JSON.read_text(encoding="utf-8")

        self.assertIn('id="gh-pat"', popup_html)
        self.assertIn('id="gh-repo"', popup_html)
        self.assertIn("gh_pat", popup_js)
        self.assertIn("gh_repo", popup_js)
        self.assertNotIn("ai_help.js", manifest_json)
        self.assertNotIn("agents/", manifest_json)

    def test_popup_retries_page_bridge_once_before_error(self) -> None:
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        self.assertIn("await sleep(800)", popup_js)
        self.assertIn('result.reason === "receiver_unavailable"', popup_js)
        self.assertIn("click the toolbar icon again", popup_js)

    def test_content_js_avoids_literal_innerhtml_assignments(self) -> None:
        sidepanel = SIDEPANEL_JS.read_text(encoding="utf-8")
        self.assertIn("errorEl.textContent = diagnosisText.length > 220", sidepanel)
        self.assertNotIn('problems-card-error").innerHTML', sidepanel)

    def test_popup_diagnostics_dump_includes_extended_debug_lines(self) -> None:
        popup_html = POPUP_HTML.read_text(encoding="utf-8")
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        self.assertIn("📋 Copy diagnostic info (paste to AI)", popup_html)
        self.assertIn("Browser user-agent:", popup_js)
        self.assertIn("Active tab URL:", popup_js)
        self.assertIn("Active tab is real http(s) page:", popup_js)
        self.assertIn("GitHub PAT present:", popup_js)
        self.assertIn("GitHub repo configured:", popup_js)
        self.assertIn("Paste this whole block to your AI assistant.", popup_js)

    def test_trainer_matches_github_parish_status(self) -> None:
        push = (REPO_ROOT / "extension" / "github_recipe_push.js").read_text(encoding="utf-8")
        sidepanel = SIDEPANEL_JS.read_text(encoding="utf-8")
        content = CONTENT_JS.read_text(encoding="utf-8")
        html = SIDEPANEL_HTML.read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("version"), "1.61.18")
        self.assertIn("ph-long-bulletin-cb", content)
        self.assertIn("max_bulletin_pages", content)
        self.assertIn("Long bulletin — allow extra pages", content)
        self.assertIn("previousTestedAt", push)
        self.assertIn("commits?path=", push)
        self.assertIn("if (!ref) return null", push)
        self.assertIn("timedOut: true", push)
        self.assertIn("formatUkDateFromIso", push)
        self.assertNotIn("_problemsDeadPollRemoved", sidepanel)
        self.assertNotIn("if (pdfOk) return { ok: true", push)
        self.assertNotIn(
            "https://raw.githubusercontent.com/${repo}/main/parishes/parish_status.json?t=${Date.now()}",
            sidepanel,
        )
        self.assertIn("_pdHarvestLabel", sidepanel)
        self.assertIn("Already working on GitHub as of", sidepanel)
        self.assertIn("trainer-version-footer", html)
        self.assertIn("Already working on GitHub as of", content)
        self.assertNotIn("parish_health", sidepanel)
        self.assertIn("Guessed bulletin link", content)
        self.assertIn("Save guessed link", content)
        self.assertIn("Use this link", content)
        self.assertIn("Yearless Sunday-16th-Aug.pdf", content)
        self.assertIn('pinLinkBtn.style.display = onDirectPdf ? "none" : "block"', content)

    def test_content_scripts_use_isolated_world_only(self) -> None:
        manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        content_scripts = manifest.get("content_scripts", [])
        for entry in content_scripts:
            self.assertNotEqual(
                entry.get("world", "ISOLATED"),
                "MAIN",
                "A content_scripts entry still has world: MAIN",
            )
        all_urls_entries = [e for e in content_scripts if "<all_urls>" in e.get("matches", [])]
        self.assertGreaterEqual(len(all_urls_entries), 1)


if __name__ == "__main__":
    unittest.main()
