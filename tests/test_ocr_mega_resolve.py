"""Tests for OCR mega-PDF source resolution after harvest."""

from __future__ import annotations

import unittest

from harvester.ocr_mega_resolve import decide_ocr_mega_source


class OcrMegaResolveTests(unittest.TestCase):
    def test_workflow_run_with_mega_uses_trigger(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_run",
            trigger_run_id="111",
            trigger_has_mega=True,
            trigger_is_full_harvest=True,
            fallback_run_id="999",
        )
        self.assertFalse(decision["skip"])
        self.assertEqual(decision["run_id"], "111")
        self.assertIn("111", decision["reason"])

    def test_single_parish_harvest_skips_ocr(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_run",
            trigger_run_id="222",
            trigger_has_mega=False,
            trigger_is_full_harvest=False,
            fallback_run_id="999",
        )
        self.assertTrue(decision["skip"])
        self.assertIsNone(decision["run_id"])
        self.assertIn("single-parish", decision["reason"].lower())

    def test_full_harvest_missing_mega_falls_back(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_run",
            trigger_run_id="333",
            trigger_has_mega=False,
            trigger_is_full_harvest=True,
            fallback_run_id="888",
        )
        self.assertFalse(decision["skip"])
        self.assertEqual(decision["run_id"], "888")
        self.assertIn("falling back", decision["reason"].lower())

    def test_full_harvest_missing_mega_and_no_fallback(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_run",
            trigger_run_id="333",
            trigger_has_mega=False,
            trigger_is_full_harvest=True,
            fallback_run_id=None,
        )
        self.assertFalse(decision["skip"])
        self.assertIsNone(decision["run_id"])
        self.assertIn("GitHub Pages", decision["reason"])

    def test_manual_dispatch_uses_latest_mega_run(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_dispatch",
            trigger_run_id=None,
            trigger_has_mega=False,
            trigger_is_full_harvest=False,
            fallback_run_id="777",
        )
        self.assertFalse(decision["skip"])
        self.assertEqual(decision["run_id"], "777")
        self.assertIn("Manual OCR", decision["reason"])

    def test_manual_dispatch_without_mega_tries_pages(self) -> None:
        decision = decide_ocr_mega_source(
            event_name="workflow_dispatch",
            fallback_run_id=None,
        )
        self.assertFalse(decision["skip"])
        self.assertIsNone(decision["run_id"])
        self.assertIn("GitHub Pages", decision["reason"])


if __name__ == "__main__":
    unittest.main()
