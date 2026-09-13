from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from ocr.generate_bulletin_pages import (
    render_bulletin_viewer_shell,
    render_parish_link_grid,
)

REPO = Path(__file__).resolve().parent.parent
VIEWER_JS = REPO / "docs" / "assets" / "pdf-inpage-viewer.js"


def _shell(*, headline: str, parish_links_html: str, ocr_fragment: str) -> str:
    return render_bulletin_viewer_shell(
        page_title=f"{headline} — test",
        diocese_label="RAPHOE",
        display_name="Raphoe Diocese",
        headline=headline,
        meta_line="This week's bulletin — 06/09/2026.",
        back_href="../../index.html",
        back_label="← Back to home",
        pdf_href="/mega_pdf/raphoe_mega_bulletin.pdf",
        pdf_download_href="/mega_pdf/raphoe_mega_bulletin.pdf",
        pdf_standalone_href="raphoe-pdf.html",
        ocr_standalone_href="raphoe-ocr.html",
        ocr_fragment=ocr_fragment,
        parish_section_heading="Raphoe parishes",
        parish_links_html=parish_links_html,
    )


def _media_1024(html: str) -> str:
    match = re.search(
        r"@media \(max-width:\s*1024px\)\s*\{(?P<body>.*?)\n\s*@media",
        html,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("missing @media (max-width: 1024px) block")
    return match.group("body")


class ViewerRulesTests(unittest.TestCase):
    """B3: locked 850/450, sticky search, new-tab links, PDF load message."""

    def test_diocese_and_parish_shells_write_locked_boxes(self) -> None:
        links = render_parish_link_grid(
            [("Annagry", "https://annagryparish.com/")],
            internal_hrefs={"annagry": "../parishes/raphoe/annagryparish.html"},
        )
        diocese = _shell(
            headline="Raphoe Collated Bulletin",
            parish_links_html=links,
            ocr_fragment="<p>Sunday Mass</p>",
        )
        parish = _shell(
            headline="Annagry Parish Bulletin",
            parish_links_html=links,
            ocr_fragment='<header class="ocr-parish-masthead"><h2>Annagry</h2></header>',
        )

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "diocese.html").write_text(diocese, encoding="utf-8")
            (out / "parish.html").write_text(parish, encoding="utf-8")
            self.assertTrue((out / "diocese.html").is_file())
            self.assertTrue((out / "parish.html").is_file())

        for html in (diocese, parish):
            self._assert_locked_desktop(html)
            self._assert_locked_phone(_media_1024(html))
            chrome_at = html.find('class="ocr-sticky-chrome"')
            panel_at = html.find('id="ocr-panel"')
            self.assertGreater(chrome_at, 0)
            self.assertGreater(panel_at, chrome_at)
            self.assertIn('id="scroll-top-btn"', html)
            self.assertIn('target="_blank" rel="noopener noreferrer"', html)
            self.assertIn("annagryparish.html", html)
            self.assertIn('target="_blank"', links)
            self.assertIn("rel=\"noopener noreferrer\"", links)
            self.assertNotIn("85vh", html)
            self.assertIn("PDF fully loaded", html)

    def test_viewer_js_locks_sizes_and_reports_load(self) -> None:
        self.assertTrue(VIEWER_JS.is_file())
        text = VIEWER_JS.read_text(encoding="utf-8")
        compact = text.replace(" ", "")
        self.assertIn("850px!important", compact)
        self.assertIn("450px!important", compact)
        self.assertIn("#ocr-panel{height:850px!important", compact)
        match = re.search(r"WHOLE_FILE_MAX\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024", text)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 24)
        self.assertIn("PDF fully loaded", text)

    def _assert_locked_desktop(self, html: str) -> None:
        for selector in (r"#ocr-panel", r"\.pdf-frame-wrap", r"\.pdf-inpage-pages"):
            self.assertRegex(html, rf"{selector}\s*\{{[^}}]*height:\s*850px")
            self.assertRegex(html, rf"{selector}\s*\{{[^}}]*min-height:\s*850px")
            self.assertRegex(html, rf"{selector}\s*\{{[^}}]*max-height:\s*850px")
        self.assertRegex(html, r"#ocr-panel\s*\{[^}]*overflow:\s*auto")
        self.assertNotRegex(html, r"#ocr-panel\s*\{[^}]*height:\s*auto")

    def _assert_locked_phone(self, media: str) -> None:
        self.assertIn("height: 450px", media)
        self.assertIn("min-height: 450px", media)
        self.assertIn("max-height: 450px", media)
        self.assertIn("#ocr-panel", media)
        self.assertIn(".pdf-frame-wrap", media)


if __name__ == "__main__":
    unittest.main()
