from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.fetcher import (
    FetchResult,
    ParishEntry,
    _fetch_entry,
    load_manual_overrides,
)
from harvester.replay import RecipeReplayError


class ManualOverrideTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_manual_overrides_filters_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parishes_dir = Path(tmp)
            (parishes_dir / "manual_overrides.json").write_text(
                json.dumps(
                    {
                        "good": {"url": "https://example.org/bulletin.pdf", "type": "download"},
                        "bad_url": {"url": "javascript:alert(1)", "type": "download"},
                        "bad_payload": "nope",
                        "unknown_type": {"url": "https://example.org/listing", "type": "mystery"},
                        "unknown_pdf": {"url": "https://example.org/current.pdf", "type": "mystery"},
                        "unknown_pdf_query": {"url": "https://example.org/current.pdf?download=1", "type": "mystery"},
                        "unknown_docx": {"url": "https://example.org/current.docx", "type": "mystery"},
                        "unknown_image": {"url": "https://example.org/current.jpg", "type": "mystery"},
                    }
                ),
                encoding="utf-8",
            )

            overrides = load_manual_overrides(parishes_dir)

            self.assertEqual(
                overrides,
                {
                    "good": {"url": "https://example.org/bulletin.pdf", "type": "download"},
                    "unknown_type": {"url": "https://example.org/listing", "type": "html"},
                    "unknown_pdf": {"url": "https://example.org/current.pdf", "type": "download"},
                    "unknown_pdf_query": {"url": "https://example.org/current.pdf?download=1", "type": "download"},
                    "unknown_docx": {"url": "https://example.org/current.docx", "type": "docx"},
                    "unknown_image": {"url": "https://example.org/current.jpg", "type": "image"},
                },
            )

    async def test_fetch_entry_prefers_manual_pdf_override_before_other_paths(self) -> None:
        entry = ParishEntry(
            key="manualtest",
            display_name="Manual Test Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
        )
        overrides = {
            "manualtest": {"url": "https://example.org/new.pdf", "type": "download"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            fake_download = AsyncMock(return_value=None)
            with (
                patch("harvester.fetcher._download_pdf", fake_download),
                patch("harvester.fetcher._is_real_pdf", return_value=True),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),  # download helper is mocked
                    manual_overrides=overrides,
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.url, "https://example.org/new.pdf")
        self.assertEqual(result.file_type, "pdf")
        fake_download.assert_awaited_once()

    async def test_fetch_entry_supports_manual_html_override(self) -> None:
        entry = ParishEntry(
            key="manualhtml",
            display_name="Manual HTML Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
        )
        overrides = {
            "manualhtml": {"url": "https://example.org/bulletins", "type": "html"},
        }

        with (
            patch(
                "harvester.fetcher._try_force_html_to_pdf",
                AsyncMock(
                    return_value=FetchResult(
                        key="manualhtml",
                        display_name="Manual HTML",
                        status="ok",
                        url="https://example.org/bulletins",
                        file_path=Path("manualhtml.pdf"),
                        file_type="html_render",
                    )
                ),
            ),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),
                    manual_overrides=overrides,
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.url, "https://example.org/bulletins")
        self.assertEqual(result.file_type, "html_render")

    async def test_fetch_entry_fails_fast_when_trained_recipe_fails(self) -> None:
        entry = ParishEntry(
            key="trainedrecipe",
            display_name="Trained Recipe Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
            bulletin_page="https://example.org/bulletins",
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            recipe_path = out_dir / "recipes" / "trainedrecipe.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(json.dumps({"steps": [{"action": "goto", "url": "https://example.org"}]}), encoding="utf-8")

            with (
                patch("harvester.fetcher.recipe_path_for", return_value=recipe_path),
                patch("harvester.fetcher.replay_recipe", AsyncMock(side_effect=RecipeReplayError("boom"))),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),
                    manual_overrides={},
                )

        self.assertEqual(result.status, "error")
        self.assertIn("Recipe replay failed", result.error or "")

    async def test_fetch_entry_skips_inactive_recipe(self) -> None:
        entry = ParishEntry(
            key="inactiveparish",
            display_name="Inactive Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/current.pdf",
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            recipe_path = out_dir / "recipes" / "inactiveparish.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(
                json.dumps(
                    {
                        "parish_key": "inactiveparish",
                        "status": "inactive",
                        "reason": "Dead website",
                    }
                ),
                encoding="utf-8",
            )
            with patch("harvester.fetcher.recipe_path_for", return_value=recipe_path):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),
                    manual_overrides={},
                )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.error, "Dead website")


if __name__ == "__main__":
    unittest.main()
