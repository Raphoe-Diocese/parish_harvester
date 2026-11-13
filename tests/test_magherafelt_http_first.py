"""Magherafelt 08/11 HTML: HTTP/1.1 short-UA GET, then print. No Playwright goto."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from harvester.replay import (
    RecipeReplayError,
    _fetch_short_ua_hit,
    _http_body_is_html,
    _inject_html_base_href,
    _recipe_http_first_html,
    replay_recipe,
)


MAGHERAFELT_URL = (
    "https://www.magherafeltparish.org/bulletin-8th-of-november-2026/"
)
MAGHERAFELT_HTML = (
    b"<!DOCTYPE html><html><head><title>Bulletin 8th of November 2026"
    b" &#8211; Magherafelt Parish</title></head><body><article>"
    b"<h1>Bulletin 8th of November 2026</h1>"
    b"<p>Masses Saturday Vigil 6.15pm Magherafelt; Sunday 9am Castledawson,"
    b" 11.30am Magherafelt. Anniversaries Sat. 7 Nov. and Sun. 8 Nov.</p>"
    b"</article></body></html>"
)


def _recipe_payload() -> dict:
    return {
        "http_first": True,
        "site_type": "wordpress",
        "playbook_type": "html_text_bulletin",
        "start_url": MAGHERAFELT_URL,
        "example_url": MAGHERAFELT_URL,
        "max_bulletin_pages": 8,
        "steps": [
            {"action": "goto", "url": MAGHERAFELT_URL},
            {"action": "print_to_pdf", "skip_listing_nav": True},
        ],
    }


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls = 0
        self.set_content_html = ""
        self.routed = []

    def on(self, _event: str, _callback) -> None:
        return None

    async def goto(self, url: str, timeout: int = 0, wait_until: str = "domcontentloaded") -> None:
        self.goto_calls += 1
        self.url = url

    async def set_content(self, html: str, wait_until: str = "load") -> None:
        self.set_content_html = html

    async def route(self, pattern: str, handler) -> None:
        self.routed.append(pattern)


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext | None = None) -> None:
        self.context = context or _FakeContext()
        self.new_context_calls = 0

    async def new_context(self, **_kwargs) -> _FakeContext:
        self.new_context_calls += 1
        return self.context


class BoomBrowser:
    async def new_context(self, **_kwargs):
        raise AssertionError("Playwright must not open when HTTP HTML GET misses")


class MagherafeltHttpFirstTests(unittest.TestCase):
    def test_recipe_flag_requires_print_step(self) -> None:
        self.assertTrue(_recipe_http_first_html(_recipe_payload()))
        self.assertFalse(_recipe_http_first_html({"http_first": True, "steps": []}))
        self.assertFalse(
            _recipe_http_first_html(
                {
                    "http_first": True,
                    "steps": [{"action": "download", "url": MAGHERAFELT_URL}],
                }
            )
        )
        self.assertFalse(_recipe_http_first_html(_recipe_payload() | {"http_first": False}))

    def test_injects_base_href_without_rewriting_body(self) -> None:
        html = _inject_html_base_href(
            MAGHERAFELT_HTML.decode("utf-8"), MAGHERAFELT_URL
        )
        self.assertIn(f'<base href="{MAGHERAFELT_URL}">', html)
        self.assertIn("Bulletin 8th of November 2026", html)
        self.assertIn("Castledawson", html)
        self.assertNotIn("15th of November", html)

    def test_html_body_check_rejects_pdf(self) -> None:
        self.assertTrue(
            _http_body_is_html(
                MAGHERAFELT_HTML, {"content-type": "text/html; charset=UTF-8"}
            )
        )
        self.assertFalse(
            _http_body_is_html(b"%PDF-1.7 fake", {"content-type": "application/pdf"})
        )

    def test_short_ua_mozilla_then_curl_returns_html(self) -> None:
        uas: list[str] = []
        page = (
            b"<!DOCTYPE HTML><html><head><title>403 Forbidden</title></head>"
            b"<body><h1>Forbidden</h1></body></html>"
        )

        def fake_urlopen(req, timeout=None, context=None, cookie_jar=None):
            ua = req.get_header("User-agent") or ""
            uas.append(ua)
            if ua == "curl/8.5.0":
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = MAGHERAFELT_HTML
                resp.headers = {"Content-Type": "text/html; charset=UTF-8"}
                resp.__enter__.return_value = resp
                resp.__exit__.return_value = False
                return resp
            raise HTTPError(
                req.full_url, 403, "Forbidden", EmailMessage(), BytesIO(page)
            )

        with patch("harvester.replay._urlopen_ipv4", side_effect=fake_urlopen):
            hit = _fetch_short_ua_hit(MAGHERAFELT_URL, 5)
        self.assertIsNotNone(hit)
        body, headers = hit
        self.assertEqual(body, MAGHERAFELT_HTML)
        self.assertIn("html", (headers.get("content-type") or "").lower())
        self.assertEqual(uas, ["Mozilla/5.0", "curl/8.5.0"])

    def test_replay_prints_fetched_html_without_goto(self) -> None:
        import asyncio

        context = _FakeContext()
        browser = _FakeBrowser(context)
        captured: dict[str, object] = {}

        async def _fake_smart_print(
            page,
            dest_path,
            _target,
            *,
            wait_ms=2500,
            skip_listing_nav=False,
            max_pages=None,
        ):
            captured["skip_listing_nav"] = skip_listing_nav
            captured["max_pages"] = max_pages
            captured["html"] = getattr(page, "set_content_html", "")
            dest_path.write_bytes(b"%PDF-1.4\n%magherafelt\n")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "magherafelt.json"
            dest = root / "out.pdf"
            recipe_path.write_text(json.dumps(_recipe_payload()), encoding="utf-8")
            with patch(
                "harvester.replay._fetch_short_ua_hit",
                return_value=(
                    MAGHERAFELT_HTML,
                    {"content-type": "text/html; charset=UTF-8"},
                ),
            ), patch(
                "harvester.replay._smart_print_page_to_pdf", _fake_smart_print
            ), patch(
                "harvester.replay._fetch_bytes_with_retries"
            ) as long_ua:
                out_path, file_type, source_url = asyncio.run(
                    replay_recipe(
                        recipe_path,
                        dest,
                        browser,
                        target_date=date(2026, 11, 8),
                    )
                )
                saved = dest.read_bytes()
                long_ua.assert_not_called()
        self.assertEqual(out_path, dest)
        self.assertEqual(file_type, "print_to_pdf")
        self.assertEqual(source_url, MAGHERAFELT_URL)
        self.assertEqual(context.page.goto_calls, 0)
        self.assertTrue(captured.get("skip_listing_nav"))
        self.assertEqual(captured.get("max_pages"), 8)
        self.assertIn("Bulletin 8th of November 2026", str(captured.get("html") or ""))
        self.assertIn("Castledawson", str(captured.get("html") or ""))
        self.assertIn(f'<base href="{MAGHERAFELT_URL}">', str(captured.get("html") or ""))
        self.assertEqual(saved, b"%PDF-1.4\n%magherafelt\n")

    def test_http_miss_fails_fast_without_playwright(self) -> None:
        import asyncio

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "magherafelt.json"
            dest = root / "out.pdf"
            recipe_path.write_text(json.dumps(_recipe_payload()), encoding="utf-8")
            with patch("harvester.replay._fetch_short_ua_hit", return_value=None):
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
        self.assertIn("bulletin-8th-of-november-2026", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
