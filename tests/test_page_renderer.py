from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.page_renderer import render_diocese_raphoe_page


class PageRendererTests(unittest.TestCase):
    def test_render_diocese_raphoe_page_uses_canonical_viewer_shell(self) -> None:
        """render_diocese_raphoe_page must build the same canonical design as
        ocr.generate_bulletin_pages.render_bulletin_viewer_shell — the single
        source of truth for every diocese's bulletin viewer page."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[
                    {"name": "Z Parish", "url": "https://example.com/z"},
                    {"name": "A Parish", "url": "https://example.com/a"},
                ],
                out_path=out_path,
                mega_pdf_url="../../mega_pdf/raphoe_mega_bulletin.pdf",
                ocr_standalone_url="../../bulletins/raphoe-2026-06-29-ocr.html",
                pdf_standalone_url="../../bulletins/raphoe-2026-06-29-pdf.html",
                ocr_text="Sunday mass at 10am",
                week_label="29/06/2026",
                diocese_display_name="Raphoe Diocese",
                headline="Raphoe Collated Bulletin",
            )
            html = out_path.read_text(encoding="utf-8")

            # Same canonical structure as the dated bulletin-archive viewer page.
            self.assertIn('id="panel-pdf"', html)
            self.assertIn('id="panel-ocr"', html)
            self.assertIn('id="ocr-panel"', html)
            self.assertIn("Open PDF", html)
            self.assertIn("Open text in new tab", html)
            self.assertIn('id="ocr-search"', html)
            self.assertIn("Tap to go to plain text bulletin", html)
            self.assertIn("mobile-jump", html)
            # Distraction-free full-page links for both PDF and OCR text.
            self.assertIn("raphoe-2026-06-29-pdf.html", html)
            self.assertIn("raphoe-2026-06-29-ocr.html", html)
            self.assertIn("Distraction-free view", html)
            self.assertIn("A Parish", html)
            self.assertIn("Z Parish", html)
            self.assertLess(html.index("A Parish"), html.index("Z Parish"))
            self.assertIn("raphoe_mega_bulletin.pdf", html)
            self.assertIn("Sunday mass at 10am", html)
            self.assertIn("← Back to home", html)

            # PDF and OCR are both always visible, stacked, no tabs/accordion
            # (Frank round-2 feedback: match his reference page layout).
            self.assertNotIn("switchTab", html)
            self.assertNotIn("tab-btn", html)
            self.assertIn("Bulletin — Original PDF Version", html)
            self.assertIn("Bulletin — OCR Extracted Plain Text", html)
            self.assertNotIn("PRO TIP", html.upper())
            self.assertNotIn("callout-tip", html)
            self.assertIn("min-height: 850px", html)
            self.assertIn("height: 850px", html)
            self.assertIn("max-height: 850px", html)
            self.assertIn("Georgia", html)

    def test_render_diocese_raphoe_page_escapes_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[{"name": "Parish <A>", "url": "https://example.com/?q=<x>"}],
                out_path=out_path,
                mega_pdf_url='../../mega_pdf/raphoe_mega_bulletin.pdf?x="1"',
                ocr_text="danger <b>tag</b>",
                ocr_is_html=False,
                diocese_display_name="Raphoe <script>",
                headline="Raphoe Collated Bulletin",
            )
            html = out_path.read_text(encoding="utf-8")

            self.assertIn("Parish &lt;A&gt;", html)
            self.assertIn("https://example.com/?q=&lt;x&gt;", html)
            self.assertIn("danger &lt;b&gt;tag&lt;/b&gt;", html)
            self.assertNotIn("danger <b>tag</b>", html)
            self.assertIn("function applyOcrSearch(query)", html)

    def test_render_diocese_raphoe_page_uses_placeholder_when_ocr_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[],
                out_path=out_path,
                mega_pdf_url="../../mega_pdf/raphoe_mega_bulletin.pdf",
                ocr_text="",
                diocese_display_name="Raphoe Diocese",
                headline="Raphoe Collated Bulletin",
            )
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("We&#x27;re still collecting OCR text for this diocese. Check back next Sunday.", html)

    def test_render_diocese_raphoe_page_links_to_internal_parish_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[
                    {"name": "Ardara", "url": "https://example.com/ardara"},
                    {"name": "Annagry", "url": "https://example.com/annagry"},
                ],
                out_path=out_path,
                mega_pdf_url="../../mega_pdf/raphoe_mega_bulletin.pdf",
                diocese_display_name="Raphoe Diocese",
                headline="Raphoe Collated Bulletin",
                internal_parish_hrefs={"ardara": "../../parishes/raphoe/ardara.html"},
            )
            html = out_path.read_text(encoding="utf-8")

            # Ardara has a generated parish page — name links to that bulletin
            # page only (no separate external "Site" link).
            self.assertIn('href="../../parishes/raphoe/ardara.html"', html)
            self.assertNotIn("🔗 Site", html)
            self.assertNotIn("parish-site-link", html)
            self.assertIn('target="_blank"', html)
            # Annagry has no generated page yet — external bulletin URL only.
            self.assertIn('href="https://example.com/annagry"', html)

    def test_render_diocese_raphoe_page_down_and_connor_ampersand(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "index.html"
            render_diocese_raphoe_page(
                parish_links=[{"name": "Antrim", "url": "https://example.com/antrim"}],
                out_path=out_path,
                mega_pdf_url="../../mega_pdf/down_and_connor_mega_bulletin.pdf",
                ocr_text="hello",
                diocese_display_name="Down and Connor",
                headline="Down & Connor Collated Bulletin",
            )
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("DOWN &amp; CONNOR", html)
            self.assertIn("Down &amp; Connor Collated Bulletin", html)


if __name__ == "__main__":
    unittest.main()
