from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.page_renderer import EMPTY_OCR_TEXT, render_diocese_page, render_diocese_raphoe_page


class PageRendererTests(unittest.TestCase):
    def test_render_diocese_page_escapes_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_page(
                diocese_key="raphoe",
                diocese_display_name="Raphoe <script>",
                mega_pdf_url='../../mega_pdf/raphoe_mega_bulletin.pdf?x="1"',
                ocr_text="danger <b>tag</b>",
                parish_links=[{"name": "Parish <A>", "url": "https://example.com/?q=<x>"}],
                out_path=out_path,
            )
            html = out_path.read_text(encoding="utf-8")

            self.assertIn("Raphoe &lt;script&gt;", html)
            self.assertIn("danger &lt;b&gt;tag&lt;/b&gt;", html)
            self.assertIn("Parish &lt;A&gt;", html)
            self.assertIn("https://example.com/?q=&lt;x&gt;", html)
            self.assertNotIn("Raphoe <script>", html)
            self.assertNotIn("danger <b>tag</b>", html)
            self.assertIn("function highlightOCR(query)", html)

    def test_render_diocese_page_uses_placeholder_when_ocr_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_page(
                diocese_key="raphoe",
                diocese_display_name="Raphoe",
                mega_pdf_url="../../mega_pdf/raphoe_mega_bulletin.pdf",
                ocr_text="",
                parish_links=[],
                out_path=out_path,
            )
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("We&#x27;re still collecting OCR text for this diocese. Check back next Sunday.", html)

    def test_render_diocese_page_renders_parish_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_page(
                diocese_key="derry",
                diocese_display_name="Derry",
                mega_pdf_url="../../mega_pdf/derry_mega_bulletin.pdf",
                ocr_text="hello",
                parish_links=[
                    {"name": "B Parish", "url": "https://example.com/b"},
                    {"name": "A Parish", "url": "https://example.com/a"},
                ],
                out_path=out_path,
            )
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("A Parish", html)
            self.assertIn("B Parish", html)
            self.assertIn("DERRY PARISHES WITH WORKING BULLETIN LINKS", html)

    def test_render_diocese_raphoe_page_stacked_layout_and_dropdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[
                    {"name": "Z Parish", "url": "https://example.com/z"},
                    {"name": "A Parish", "url": "https://example.com/a"},
                ],
                out_path=out_path,
                mega_pdf_url="../../mega_pdf/raphoe_mega_bulletin.pdf",
                ocr_text="Sunday mass at 10am",
            )
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("Go to OCR version", html)
            self.assertIn('id="ocr-section"', html)
            self.assertIn("parish-accordion", html)
            self.assertIn("parish-link-grid", html)
            self.assertNotIn("parish-select", html)
            self.assertIn("A Parish", html)
            self.assertIn("Z Parish", html)
            self.assertLess(html.index("A Parish"), html.index("Z Parish"))
            self.assertIn("raphoe_mega_bulletin.pdf", html)
            self.assertIn("Sunday mass at 10am", html)


if __name__ == "__main__":
    unittest.main()
