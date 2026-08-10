from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from harvester.replay import (
    _find_mdocs_pdf_urls,
    _find_pdfemb_url,
    _is_non_bulletin_url,
    _recipe_navigation_wait_until,
    _score_bulletin_url,
    replay_recipe,
)


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.org/start"
        self._screenshot = None
        self._pdf = b"%PDF-1.4\n%fake\n"
        self.last_goto_timeout = None
        self.goto_calls = 0

    def on(self, _event: str, _callback) -> None:
        return None

    def locator(self, _selector: str):
        class _FakeLocator:
            @property
            def first(self):
                return self

            async def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

        return _FakeLocator()

    async def goto(self, url: str, timeout: int = 0, wait_until: str = "domcontentloaded") -> None:
        self.goto_calls += 1
        self.url = url
        self.last_goto_timeout = timeout

    async def wait_for_load_state(self, _state: str, timeout: int = 0) -> None:
        return None

    async def screenshot(self, full_page: bool = False) -> bytes:
        if self._screenshot is None:
            img = Image.new("RGB", (120, 120), color=(255, 255, 255))
            buf = BytesIO()
            img.save(buf, format="PNG")
            self._screenshot = buf.getvalue()
        return self._screenshot

    async def pdf(self, **_kwargs) -> bytes:
        return self._pdf


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context

    async def new_context(self, accept_downloads: bool = True) -> _FakeContext:
        self.context.accept_downloads = accept_downloads
        return self.context


class ClaudyBulletinFilterTests(unittest.TestCase):
    def test_gdpr_pdf_is_non_bulletin(self) -> None:
        url = "http://parishofclaudy.com/onewebmedia/Diocese%20of%20Derry%20-%20GDPR%20Guide.pdf"
        self.assertTrue(_is_non_bulletin_url(url))

    def test_newsletter_docx_is_bulletin(self) -> None:
        url = "http://parishofclaudy.com/onewebmedia/NEWSLETTER%207-6-26.docx"
        self.assertFalse(_is_non_bulletin_url(url))

    def test_newer_newsletter_scores_higher(self) -> None:
        older = _score_bulletin_url("http://x/onewebmedia/NEWSLETTER%2031-5-26.docx")
        newer = _score_bulletin_url("http://x/onewebmedia/NEWSLETTER%2014-6-26.docx")
        self.assertGreater(newer[0], older[0])

    def test_recent_undated_slug_outscores_old_dated_slug(self) -> None:
        # glenariffeparish 2026-08-09: the current bulletin's WordPress slug
        # is named after the liturgical feast ("Sixteenth-Sunday-of-Ordinary
        # -Time.pdf", no date at all) while an archived bulletin from over a
        # year earlier has an explicit date in its filename. Without a floor
        # based on the /uploads/YYYY/MM/ folder, the old-but-dated file always
        # outscored the current-but-undated one, so the fallback grabbed a
        # 2025 Easter bulletin instead of the current one.
        current = _score_bulletin_url(
            "https://glenariffeparish.org/wp-content/uploads/2026/07/"
            "Sixteenth-Sunday-of-Ordinary-Time.pdf"
        )
        old_dated = _score_bulletin_url(
            "https://glenariffeparish.org/wp-content/uploads/2025/04/"
            "Easter-Sunday-20th-April-2025.pdf"
        )
        self.assertGreater(current[0], old_dated[0])

    def test_opaque_hash_does_not_inflate_bulletin_score(self) -> None:
        # carrickparish.org 2026-08-09: a Wix hashed filename can contain a
        # coincidental 6-digit run that looks like a DDMMYY date.
        hashed = _score_bulletin_url(
            "https://www.carrickparish.org/_files/ugd/"
            "15976c_67e290776b824ccfb8ce43943f2620aa.pdf"
        )
        self.assertEqual(hashed[0], 0)

    def test_dd_mm_yy_dot_filename_outscores_yy_mm_dd_misreading(self) -> None:
        # stbrigidsparishbelfast.org 2026-08-09: UK-convention DD.MM.YY
        # filenames ("09.08.26") collide with the YY.MM.DD dot pattern used
        # for Google Drive folder rows. Reading "09.08.26" as YY.MM.DD gives
        # a bogus 2009-08-26, which lost to an older bulletin whose digits
        # happened to parse as a "newer-looking" fake YY.MM.DD year
        # (26.07.26 -> 2026-07-26). Both interpretations must be scored so
        # the genuinely current bulletin wins.
        current = _score_bulletin_url(
            "https://stbrigidsparishbelfast.org/assets/documents/"
            "Parish-Bulletin-09.08.26-FOR-PRINTING.pdf"
        )
        older = _score_bulletin_url(
            "https://stbrigidsparishbelfast.org/assets/documents/"
            "Parish-Bulletin-26.07.26-FOR-PRINTING.pdf"
        )
        self.assertEqual(current[0], 20260809)
        self.assertEqual(older[0], 20260726)
        self.assertGreater(current[0], older[0])

    async def test_find_pdfemb_url_prefers_pdf_embedder_links(self) -> None:
        class _Page:
            url = "https://example.org/news/"

            async def eval_on_selector_all(self, selector: str, _script: str):
                self.selector = selector
                return ["/wp-content/uploads/2026/04/bulletin.pdf", "/other.html"]

        page = _Page()
        found = await _find_pdfemb_url(page)
        self.assertEqual(page.selector, "a.pdfemb-viewer[href]")
        self.assertEqual(found, "https://example.org/wp-content/uploads/2026/04/bulletin.pdf")

    async def test_replay_recipe_supports_html_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps({"steps": [{"action": "html", "url": "https://example.org/bulletin"}]}),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "print_to_pdf")
            self.assertEqual(source_url, "https://example.org/bulletin")
            self.assertTrue(dest.exists())

    async def test_replay_recipe_uses_recipe_timeout_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "timeout": 30000,
                        "steps": [
                            {"action": "goto", "url": "https://example.org/news"},
                            {"action": "html", "url": "https://example.org/news"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            _out_path, _file_type, _source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(context.page.last_goto_timeout, 30000)

    async def test_replay_recipe_supports_image_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps({"steps": [{"action": "image", "url": "https://example.org/bulletin.jpg"}]}),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            fake_download = AsyncMock(return_value=("https://example.org/bulletin.jpg", "image_to_pdf"))
            with patch("harvester.replay._download_image_url_as_pdf", fake_download):
                out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "image_to_pdf")
            self.assertEqual(source_url, "https://example.org/bulletin.jpg")
            self.assertTrue(context.accept_downloads)
            fake_download.assert_awaited_once()
            self.assertTrue(context.closed)

    def test_replay_recipe_supports_image_stack_step(self) -> None:
        import asyncio

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "steps": [
                            {"action": "goto", "url": "https://example.org/bulletins/"},
                            {"action": "image_stack", "count": 2},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            fake_find = AsyncMock(
                return_value=[
                    "https://example.org/b1.jpg",
                    "https://example.org/b2.jpg",
                ]
            )
            fake_stack = AsyncMock(return_value=("https://example.org/b1.jpg", "image_to_pdf"))
            with patch("harvester.replay._find_stacked_bulletin_image_urls", fake_find):
                with patch("harvester.replay._download_image_urls_as_pdf", fake_stack):
                    out_path, file_type, source_url = asyncio.run(
                        replay_recipe(recipe_path, dest, browser)
                    )

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "image_to_pdf")
            self.assertEqual(source_url, "https://example.org/b1.jpg")
            fake_find.assert_awaited_once()
            fake_stack.assert_awaited_once()
            self.assertTrue(context.closed)

    def test_find_stacked_bulletin_image_urls_keeps_dom_order(self) -> None:
        import asyncio

        from harvester.replay import _find_stacked_bulletin_image_urls

        class _Page:
            url = "https://example.org/bulletins/"

            async def eval_on_selector_all(self, selector: str, _script: str):
                self.selector = selector
                return [
                    {
                        "index": 2,
                        "src": "/wp-content/uploads/2026/06/second.jpg",
                        "naturalWidth": 900,
                        "naturalHeight": 1200,
                    },
                    {
                        "index": 0,
                        "src": "/wp-content/uploads/2026/06/first.jpg",
                        "naturalWidth": 900,
                        "naturalHeight": 1200,
                    },
                    {
                        "index": 1,
                        "src": "/logo.png",
                        "naturalWidth": 120,
                        "naturalHeight": 80,
                    },
                ]

        page = _Page()
        urls = asyncio.run(_find_stacked_bulletin_image_urls(page, 2))
        self.assertEqual(
            urls,
            [
                "https://example.org/wp-content/uploads/2026/06/first.jpg",
                "https://example.org/wp-content/uploads/2026/06/second.jpg",
            ],
        )
        self.assertEqual(page.selector, "img")

    def test_find_stacked_bulletin_image_urls_falls_back_for_lazy_loaded_images(self) -> None:
        """Lazy-loaded <img> tags report naturalWidth/naturalHeight as 0 until
        the browser decodes them. The eval_on_selector_all JS must fall back
        to the rendered box size / width-height attributes so a genuine
        not-yet-loaded bulletin scan isn't dropped as "too small"."""
        import asyncio

        from harvester.replay import _find_stacked_bulletin_image_urls

        class _Page:
            url = "https://example.org/bulletins/"
            captured_script = ""

            async def eval_on_selector_all(self, selector: str, script: str):
                self.selector = selector
                self.captured_script = script
                return [
                    {
                        "index": 0,
                        "src": "/wp-content/uploads/2026/06/lazy-bulletin.jpg",
                        # Not yet decoded: natural size is 0, but the fallback
                        # logic should recover a usable size from these.
                        "naturalWidth": 900,
                        "naturalHeight": 1200,
                    },
                ]

        page = _Page()
        urls = asyncio.run(_find_stacked_bulletin_image_urls(page, 1))
        self.assertEqual(
            urls,
            ["https://example.org/wp-content/uploads/2026/06/lazy-bulletin.jpg"],
        )
        # The eval_on_selector_all mock above bypasses real browser JS
        # execution (it returns canned dimensions directly), so it can't
        # exercise the lazy-load fallback at runtime. Assert the fallback is
        # actually present in the JS sent to the page, so removing it would
        # fail this test.
        script = page.captured_script
        self.assertIn("naturalWidth", script)
        self.assertIn("offsetWidth", script)
        self.assertIn("offsetHeight", script)
        self.assertIn("getAttribute('width')", script)
        self.assertIn("getAttribute('height')", script)

    def test_find_stacked_bulletin_image_urls_supports_last_position(self) -> None:
        import asyncio

        from harvester.replay import _find_stacked_bulletin_image_urls

        class _Page:
            url = "https://example.org/"

            async def eval_on_selector_all(self, selector: str, _script: str):
                return [
                    {"index": 0, "src": "/old-a.jpg", "naturalWidth": 900, "naturalHeight": 1200},
                    {"index": 1, "src": "/old-b.jpg", "naturalWidth": 900, "naturalHeight": 1200},
                    {"index": 2, "src": "/new-1.jpg", "naturalWidth": 900, "naturalHeight": 1200},
                    {"index": 3, "src": "/new-2.jpg", "naturalWidth": 900, "naturalHeight": 1200},
                ]

        page = _Page()
        urls = asyncio.run(
            _find_stacked_bulletin_image_urls(page, 2, position="last")
        )
        self.assertEqual(
            urls,
            [
                "https://example.org/new-1.jpg",
                "https://example.org/new-2.jpg",
            ],
        )

    async def test_replay_recipe_supports_print_to_pdf_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "steps": [
                            {"action": "goto", "url": "https://example.org/news"},
                            {"action": "print_to_pdf"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "print_to_pdf")
            self.assertEqual(source_url, "https://example.org/news")
            self.assertTrue(dest.exists())
            self.assertEqual(dest.read_bytes(), context.page._pdf)
            self.assertEqual(context.page.goto_calls, 1)
            self.assertTrue(context.closed)

    async def test_replay_recipe_supports_crop_screenshot_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "action": "crop_screenshot",
                                "x": 10,
                                "y": 10,
                                "width": 50,
                                "height": 40,
                                "page_x": 10,
                                "page_y": 10,
                                "element_selector": "img",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "crop_screenshot_to_pdf")
            self.assertEqual(source_url, "https://example.org/start")
            self.assertTrue(dest.exists())
            self.assertGreater(dest.stat().st_size, 0)
            self.assertTrue(context.closed)

    def test_replay_auto_goto_start_url_before_click(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe_path = Path(tmp) / "threepatrons.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "start_url": "https://threepatrons.org/",
                        "steps": [
                            {"action": "click", "selector": "a.mod_downloadlink"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dest = Path(tmp) / "threepatrons.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)
            page = context.page

            async def _fake_dropfiles(_page, _dest, _timeout):
                _dest.write_bytes(b"%PDF-1.4\n%fake-bulletin\n")
                return "https://threepatrons.org/files/10/Weekly-Bulletins/104/", "pdf"

            with patch(
                "harvester.replay._try_joomla_dropfiles_click_download",
                new=AsyncMock(side_effect=_fake_dropfiles),
            ):
                import asyncio

                out_path, file_type, source_url = asyncio.run(
                    replay_recipe(
                        recipe_path=recipe_path,
                        dest=dest,
                        browser=browser,
                    )
                )

            self.assertEqual(page.goto_calls, 1)
            self.assertEqual(page.url, "https://threepatrons.org/")
            self.assertEqual(file_type, "pdf")
            self.assertIn("Weekly-Bulletins", source_url)


class TestNavigationWaitUntil(unittest.TestCase):
    def test_recipe_navigation_wait_until_reads_recipe_field(self) -> None:
        self.assertEqual(
            _recipe_navigation_wait_until({"navigation_wait_until": "commit"}),
            "commit",
        )

    def test_replay_goto_uses_commit_when_recipe_requests_it(self) -> None:
        import asyncio

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "navigation_wait_until": "commit",
                        "timeout_ms": 120000,
                        "steps": [
                            {"action": "goto", "url": "https://derriaghycatholicparish.com/?page_id=262"},
                            {"action": "image_stack", "count": 2},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakePageContext()
            browser = _FakeBrowser(context)
            fake_find = AsyncMock(
                return_value=[
                    "https://example.org/b1.jpg",
                    "https://example.org/b2.jpg",
                ]
            )
            fake_stack = AsyncMock(return_value=("https://example.org/b1.jpg", "image_to_pdf"))
            with patch("harvester.replay._find_stacked_bulletin_image_urls", fake_find):
                with patch("harvester.replay._download_image_urls_as_pdf", fake_stack):
                    asyncio.run(replay_recipe(recipe_path, dest, browser))

            page = context.page
            self.assertEqual(page.goto_calls, 1)
            self.assertEqual(page.last_wait_until, "commit")

    def test_find_mdocs_pdf_urls_prefers_newest_dated_pdf(self) -> None:
        import asyncio

        class _MdocsPage:
            url = "http://portstewartparish.website/bulletins/"

            async def eval_on_selector_all(self, _selector: str, _js: str):
                return [
                    "/wp-content/mdocs-previews/21st-june-2026.pdf",
                    "/wp-content/mdocs-previews/14th-june-2026.pdf",
                ]

        found = asyncio.run(_find_mdocs_pdf_urls(_MdocsPage()))
        self.assertTrue(found)
        self.assertIn("21st-june-2026", found[0])


class _FakePageContext:
    def __init__(self) -> None:
        self.page = _FakePageWithWaitUntil()
        self.accept_downloads = False
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakePageWithWaitUntil(_FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.last_wait_until = ""

    async def goto(self, url: str, timeout: int = 0, wait_until: str = "domcontentloaded") -> None:
        self.last_wait_until = wait_until
        await super().goto(url, timeout=timeout, wait_until=wait_until)


if __name__ == "__main__":
    unittest.main()
