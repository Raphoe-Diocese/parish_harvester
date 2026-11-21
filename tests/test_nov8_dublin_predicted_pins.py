"""13/11/2026: Dublin predicted_dated_pdf misses. Pin proved files. Not predicted."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


def _load(rel: str) -> dict:
    return json.loads((Path("parishes/recipes") / rel).read_text(encoding="utf-8-sig"))


class Nov8DublinPredictedPinTests(unittest.TestCase):
    def _assert_wordpress_pin(self, recipe: dict, needle: str) -> None:
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertIn(needle, recipe["start_url"])
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertEqual(recipe["steps"][1]["action"], "download")
        self.assertIn(needle, recipe["steps"][0]["url"])
        self.assertIn(needle, recipe["steps"][1]["url"])
        self.assertTrue(recipe["steps"][1].get("use_captured_url"))

    def test_sandyford_pins_8_november_pdf(self) -> None:
        recipe = _load("dublin/sandyford.json")
        self._assert_wordpress_pin(recipe, "Newsletter-2026-11-08.pdf")
        self.assertNotIn("2026-11-01", recipe["start_url"])
        self.assertNotIn("November-1st", recipe["start_url"])
        self.assertTrue(recipe["start_url"].lower().endswith(".pdf"))

    def test_foxrock_uses_dated_media_titles_without_looking_ahead(self) -> None:
        recipe = _load("dublin/foxrock.json")
        self.assertEqual(recipe["start_url"], "https://foxrockparish.ie/news/")
        self.assertEqual(recipe["site_type"], "wp_json_newest_media")
        self.assertEqual(recipe["href_patterns"], ["Parish newsletter"])
        self.assertEqual(recipe["weeks_ahead"], 0)
        self.assertIn("Share2026", recipe["href_skip_patterns"])
        self.assertFalse(recipe.get("skip"))

    def test_foxrock_media_titles_select_requested_sunday(self) -> None:
        import asyncio
        import tempfile
        from datetime import date
        from unittest.mock import AsyncMock, patch

        from harvester.replay import replay_recipe

        urls = {
            15: "https://foxrockparish.ie/wp-content/uploads/2026/11/00-6deb3f519f45.pdf",
            22: "https://foxrockparish.ie/wp-content/uploads/2026/11/00-f628df971e80.pdf",
        }
        payload = [
            {"source_url": url, "title": {"rendered": f"Parish newsletter 2026-11-{day}"}}
            for day, url in urls.items()
        ]

        def fetch(url, **_kwargs):
            if "media_type=application" in url:
                return json.dumps(payload).encode(), {"content-type": "application/json"}
            if url in urls.values():
                return b"%PDF-1.7 mock newsletter", {"content-type": "application/pdf"}
            return None

        with tempfile.TemporaryDirectory() as tmp, patch(
            "harvester.replay._try_sunday_upload_pdf", new_callable=AsyncMock,
            return_value=None,
        ), patch("harvester.replay._fetch_bytes_with_retries", side_effect=fetch):
            for day, url in urls.items():
                with self.subTest(day=day):
                    destination = Path(tmp) / f"foxrock-{day}.pdf"
                    result = asyncio.run(replay_recipe(
                        Path("parishes/recipes/dublin/foxrock.json"),
                        destination,
                        None,
                        target_date=date(2026, 11, day),
                    ))
                    self.assertEqual(result, (destination, "pdf", url))

    def test_foxrock_last_week_pin_is_fetched_over_http(self) -> None:
        import asyncio
        import tempfile
        from datetime import date
        from unittest.mock import AsyncMock, patch

        from harvester.replay import replay_recipe

        pin = (
            "https://foxrockparish.ie/wp-content/uploads/2026/10/"
            "Newsletter-November-1st-2026.pdf"
        )

        class BoomBrowser:
            async def new_context(self, **_kwargs):
                raise AssertionError("Playwright must not open for Foxrock HTTP")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "foxrock.json"
            dest = root / "out.pdf"
            recipe_path.write_text(
                json.dumps(
                    {
                        "playbook_type": "direct_download",
                        "ignore_https_errors": True,
                        "skip": False,
                        "start_url": pin,
                        "example_url": pin,
                        "steps": [
                            {
                                "action": "download",
                                "url": pin,
                                "use_captured_url": True,
                                "skip_listing_nav": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "harvester.replay._try_http_document_url",
                new_callable=AsyncMock,
                return_value=(pin, "pdf"),
            ) as http:
                _dest_out, kind, url = asyncio.run(
                    replay_recipe(
                        recipe_path,
                        dest,
                        BoomBrowser(),
                        target_date=date(2026, 11, 8),
                    )
                )
        self.assertEqual(kind, "pdf")
        self.assertEqual(url, pin)
        http.assert_awaited()
        self.assertEqual(http.await_args.args[0], pin)

    def test_foxrock_http_403_does_not_open_playwright(self) -> None:
        import asyncio
        import tempfile
        from datetime import date
        from unittest.mock import AsyncMock, patch

        from harvester.replay import RecipeReplayError, replay_recipe

        pin = (
            "https://foxrockparish.ie/wp-content/uploads/2026/10/"
            "Newsletter-November-1st-2026.pdf"
        )

        class BoomBrowser:
            async def new_context(self, **_kwargs):
                raise AssertionError("Playwright must not open for a WAF-blocked PDF")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "foxrock.json"
            dest = root / "out.pdf"
            recipe_path.write_text(
                json.dumps(
                    {
                        "playbook_type": "direct_download",
                        "ignore_https_errors": True,
                        "skip": False,
                        "start_url": pin,
                        "example_url": pin,
                        "steps": [
                            {
                                "action": "download",
                                "url": pin,
                                "use_captured_url": True,
                                "skip_listing_nav": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "harvester.replay._try_http_document_url",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with self.assertRaises(RecipeReplayError) as ctx:
                    asyncio.run(
                        replay_recipe(
                            recipe_path,
                            dest,
                            BoomBrowser(),
                            target_date=date(2026, 11, 8),
                        )
                    )
        self.assertIn("browser was not opened", str(ctx.exception).lower())
        self.assertIn("Newsletter-November-1st-2026.pdf", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
