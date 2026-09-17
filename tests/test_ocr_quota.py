from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ocr.quota_log import (
    billed_pages,
    ceiling_for,
    markdown_section,
    project_to_26,
    provider_key,
    record_pages,
)


SEP = datetime(2026, 9, 15, tzinfo=timezone.utc)


class ProviderKeyTests(unittest.TestCase):
    def test_api_names(self) -> None:
        self.assertEqual(provider_key("Mistral"), "mistral")
        self.assertEqual(provider_key("Tier0+Gemini fallback"), "gemini")
        self.assertEqual(provider_key("OpenAI fallback"), "openai")

    def test_tesseract_never_counts(self) -> None:
        self.assertIsNone(provider_key("tesseract"))
        self.assertIsNone(provider_key("Tier0-text"))
        self.assertIsNone(provider_key("GitHub Models fallback"))
        key, pages = billed_pages("tesseract", [["a"]], [0, 1])
        self.assertIsNone(key)
        self.assertEqual(pages, 0)


class BillingTests(unittest.TestCase):
    def test_sparse_counts_vision_indexes_only(self) -> None:
        key, pages = billed_pages("Gemini fallback", [["x"]] * 20, [3, 7])
        self.assertEqual(key, "gemini")
        self.assertEqual(pages, 2)

    def test_full_mistral_counts_all_pages(self) -> None:
        key, pages = billed_pages("Mistral", [["a"], ["b"], ["c"]], None)
        self.assertEqual(key, "mistral")
        self.assertEqual(pages, 3)


class ProjectionTests(unittest.TestCase):
    def test_four_to_twenty_six(self) -> None:
        self.assertEqual(project_to_26(8, 4), 52)

    def test_unknown_when_no_dioceses(self) -> None:
        self.assertIsNone(project_to_26(8, 0))


class CeilingTests(unittest.TestCase):
    def test_mistral_uses_published_free_pages(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ceiling_for("mistral"), 2500)
            self.assertIsNone(ceiling_for("gemini"))

    def test_reads_positive_env(self) -> None:
        with patch.dict(os.environ, {"OCR_CEILING_GEMINI": "100"}, clear=False):
            self.assertEqual(ceiling_for("gemini"), 100)


class DashboardTests(unittest.TestCase):
    def test_three_numbers_and_unknown_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "parishes").mkdir()
            (root / "parishes" / "dioceses.json").write_text(
                json.dumps(
                    {
                        "dioceses": [
                            {"key": "a"},
                            {"key": "b"},
                            {"key": "c"},
                            {"key": "d"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            record_pages("Mistral", 4, root=root, now=SEP)
            record_pages("Gemini", 2, root=root, now=SEP)
            with patch.dict(os.environ, {}, clear=True):
                text = markdown_section(root, now=SEP)
            self.assertIn("| Mistral | 4 | 2500 | 0.2% | 26 |", text)
            self.assertIn("| Gemini | 2 | unknown | unknown | 13 |", text)
            self.assertIn("| OpenAI | 0 | unknown | unknown | 0 |", text)
            self.assertIn("Tesseract is not a bulletin reader", text)
            self.assertNotIn("over ceiling", text)

    def test_red_when_projection_over_known_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "parishes").mkdir()
            (root / "parishes" / "dioceses.json").write_text(
                json.dumps({"dioceses": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}]}),
                encoding="utf-8",
            )
            record_pages("OpenAI", 8, root=root, now=SEP)
            with patch.dict(os.environ, {"OCR_CEILING_OPENAI": "20"}, clear=False):
                text = markdown_section(root, now=SEP)
            self.assertIn("🔴", text)
            self.assertIn("over ceiling", text)


if __name__ == "__main__":
    unittest.main()
