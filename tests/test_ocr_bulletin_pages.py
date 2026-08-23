from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ocr.generate_bulletin_pages import (
    DioceseConfig,
    _fragment_to_plain_text,
    build_az_parish_ocr_html,
    extract_ocr_fragment,
    format_uk_date,
    parse_parish_links,
    pdf_inpage_viewer_boot_js,
    pdf_inpage_viewer_css,
    pdf_inpage_viewer_html,
    pdf_mobile_fallback_boot_js,
    pdf_mobile_fallback_css,
    pdf_mobile_fallback_html,
    prefers_native_pdf_js,
    prepare_ocr_fragment,
    render_bulletin_viewer_shell,
    render_ocr_standalone_page,
    render_pdf_standalone_page,
    render_viewer_page,
)


class OcrBulletinPageTests(unittest.TestCase):
    def test_format_uk_date(self) -> None:
        self.assertEqual(format_uk_date("2026-05-21"), "21/05/2026")
        self.assertEqual(format_uk_date("bad-date"), "bad-date")

    def test_fragment_to_plain_text_unescapes_double_encoded_entities(self) -> None:
        plain = _fragment_to_plain_text("St. Mary&amp;#x27;s Church")
        self.assertIn("St. Mary's Church", plain)
        self.assertNotIn("&amp;", plain)
        self.assertNotIn("&#x27;", plain)

    def test_parse_parish_links_uses_first_url_after_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "bulletin_urls.txt"
            evidence.write_text(
                "# --- Parish One ---\n"
                "# comment\n"
                "https://example.com/one\n"
                "https://example.com/one-older\n"
                "\n"
                "# --- Parish Two ---\n"
                "https://example.com/two\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_parish_links(evidence),
                [
                    ("Parish One", "https://example.com/one"),
                    ("Parish Two", "https://example.com/two"),
                ],
            )

    def test_extract_ocr_fragment_and_render_viewer_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ocr_html = tmp / "bulletin.html"
            ocr_html.write_text(
                "<html><body><div class=\"scrollable-viewer\">"
                "<h2>Page 1</h2><p>Call 028 1234 5678</p><hr><h2>Page 2</h2><p>Email test@example.com</p>"
                "</div></body></html>",
                encoding="utf-8",
            )
            fragment = extract_ocr_fragment(ocr_html)
            self.assertIn("<h3>PAGE 1</h3>", fragment)
            self.assertIn("<h3>PAGE 2</h3>", fragment)

            config = DioceseConfig(
                key="test",
                display_name="Test Diocese",
                headline="TEST DIOCESE BIG BULLETIN",
                evidence_path=tmp / "unused.txt",
                pdf_filename="test_mega_bulletin.pdf",
            )

            html_output = render_viewer_page(
                config=config,
                bulletin_date="2026-05-19",
                page_count=2,
                ocr_fragment=fragment,
                parish_links=[("Parish One", "https://example.com/one")],
            )

            self.assertIn("TEST COLLATED BULLETIN", html_output)
            self.assertIn("../mega_pdf/test_mega_bulletin.pdf", html_output)
            self.assertIn("PARISHES WITH WORKING BULLETIN LINKS", html_output.upper())
            self.assertIn("https://example.com/one", html_output)
            self.assertIn("Generated for 19/05/2026.", html_output)
            self.assertIn("id=\"ocr-match-count\"", html_output)
            self.assertIn("id=\"ocr-prev\"", html_output)
            self.assertIn("id=\"ocr-next\"", html_output)
            self.assertNotIn("Jump to OCR Text", html_output)
            self.assertIn("Tap to go to plain text bulletin", html_output)
            self.assertIn("mobile-jump", html_output)
            self.assertIn('href="#panel-ocr"', html_output)
            self.assertIn("test-2026-05-19-ocr.html", html_output)
            self.assertNotIn("Next page →", html_output)
            self.assertNotIn("pdf-controls", html_output)
            self.assertIn("pdf-frame-wrap", html_output)
            self.assertIn('target="_blank"', html_output)
            # Quiet new-tab links for PDF / distraction-free / OCR text.
            self.assertIn("test-2026-05-19-pdf.html", html_output)
            self.assertIn("Distraction-free view", html_output)
            self.assertIn("test-2026-05-19-ocr.html", html_output)
            self.assertIn("Open PDF", html_output)
            self.assertIn("Open text in new tab", html_output)
            # OCR search must remain available.
            self.assertIn('id="ocr-search"', html_output)
            self.assertIn('id="ocr-prev"', html_output)
            self.assertIn('id="ocr-next"', html_output)
            # PDF is shown immediately (no tab click) — the PDF and OCR
            # panels are both always visible, stacked, matching Frank's
            # reference page layout (Frank feedback, round 2).
            self.assertNotIn("switchTab", html_output)
            self.assertNotIn("tab-btn", html_output)
            self.assertNotIn('role="tablist"', html_output)
            self.assertIn("Bulletin — Original PDF Version", html_output)
            self.assertIn("Bulletin — OCR Extracted Plain Text", html_output)
            self.assertNotIn("PRO TIP", html_output.upper())
            self.assertNotIn("callout-tip", html_output)
            self.assertNotIn("🔗 Site", html_output)
            self.assertIn("min-height: 850px", html_output)
            self.assertIn("height: 850px", html_output)
            self.assertIn("max-height: 850px", html_output)
            self.assertRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*min-height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*max-height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*overflow:\s*auto",
            )
            self.assertRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*overflow-y:\s*auto",
            )
            self.assertNotRegex(
                html_output,
                r"#ocr-panel\s*\{[^}]*height:\s*auto",
            )
            self.assertRegex(
                html_output,
                r"\.pdf-frame-wrap\s*\{[^}]*min-height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"\.pdf-inpage-pages\s*\{[^}]*min-height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px",
            )
            self.assertRegex(
                html_output,
                r"\.pdf-inpage-pages\s*\{[^}]*overflow:\s*auto",
            )
            self.assertNotRegex(
                html_output,
                r"\.pdf-inpage-pages\s*\{[^}]*height:\s*auto",
            )
            self.assertNotIn("85vh", html_output)
            # Tablet/phone: locked 450px visible boxes (not desktop 850px).
            self.assertIn("@media (max-width: 1024px)", html_output)
            self.assertIn("min-height: 450px", html_output)
            self.assertIn("height: 450px", html_output)
            self.assertIn("max-height: 450px", html_output)
            self.assertIn("Georgia", html_output)
            self.assertIn("Download PDF", html_output)
            self.assertIn("pdf-fullscreen-btn", html_output)
            # Desktop + mobile: hide the raw-PDF iframe and show stacked PDF.js pages.
            self.assertIn("pdf-inpage-viewer", html_output)
            self.assertIn("/assets/pdf-inpage-viewer.js?v=20260823s", html_output)
            self.assertIn("data-pdf-src", html_output)
            self.assertIn("is-native-pdf", html_output)
            self.assertIn("display: flex !important", html_output)
            self.assertIn(".pdf-frame-wrap iframe", html_output)
            self.assertIn("display: none !important", html_output)
            self.assertNotIn("pdf-inpage-prev", html_output)
            self.assertNotIn("pdf-inpage-next", html_output)
            self.assertNotIn("pdf-inpage-page-label", html_output)
            self.assertNotIn("pdf-inpage-nav", html_output)
            media_idx = html_output.find("@media (max-width: 1024px)")
            self.assertGreaterEqual(media_idx, 0)
            media_chunk = html_output[media_idx : media_idx + 900]
            self.assertIn("min-height: 450px", media_chunk)
            self.assertNotIn('id="pdf-inpage-viewer" hidden', html_output)
            # PDF section must appear before the OCR section in document order.
            self.assertLess(
                html_output.index("Bulletin — Original PDF Version"),
                html_output.index("Bulletin — OCR Extracted Plain Text"),
            )

    def test_render_pdf_standalone_page(self) -> None:
        config = DioceseConfig(
            key="test",
            display_name="Test Diocese",
            headline="TEST DIOCESE BIG BULLETIN",
            evidence_path=Path("unused.txt"),
            pdf_filename="test_mega_bulletin.pdf",
        )
        html_output = render_pdf_standalone_page(
            config=config,
            bulletin_date="2026-05-19",
            pdf_href="../mega_pdf/test_mega_bulletin.pdf",
            viewer_href="test-2026-05-19.html",
        )
        self.assertIn("../mega_pdf/test_mega_bulletin.pdf", html_output)
        self.assertIn('href="test-2026-05-19.html"', html_output)
        self.assertIn("<iframe", html_output)
        self.assertIn("embed-mode", html_output)
        self.assertIn("pdf-inpage-viewer", html_output)
        self.assertIn("/assets/pdf-inpage-viewer.js?v=20260823s", html_output)
        self.assertIn("data-pdf-src", html_output)
        self.assertNotIn("pdf-inpage-prev", html_output)
        self.assertNotIn("pdf-inpage-next", html_output)
        self.assertNotIn("pdf-inpage-page-label", html_output)

    def test_mobile_pdf_inpage_viewer_helpers(self) -> None:
        """PDF.js in-page viewer stacks pages for scroll; Open PDF / Download stay."""
        det = prefers_native_pdf_js()
        self.assertIn("prefersNativePdf", det)
        self.assertIn("Android", det)
        self.assertIn("iPhone", det)
        self.assertIn("maxTouchPoints", det)

        panel = pdf_inpage_viewer_html("../mega_pdf/raphoe_mega_bulletin.pdf")
        self.assertIn('id="pdf-inpage-viewer"', panel)
        self.assertIn('data-pdf-src="../mega_pdf/raphoe_mega_bulletin.pdf"', panel)
        self.assertIn("pdf-inpage-pages", panel)
        self.assertIn("Open PDF", panel)
        self.assertIn("Download", panel)
        self.assertIn('target="_blank"', panel)
        self.assertNotIn("pdf-inpage-prev", panel)
        self.assertNotIn("pdf-inpage-next", panel)
        self.assertNotIn("pdf-inpage-page-label", panel)
        self.assertNotIn("Previous page", panel)
        self.assertNotIn("Next page", panel)
        self.assertEqual(panel, pdf_mobile_fallback_html("../mega_pdf/raphoe_mega_bulletin.pdf"))

        boot = pdf_inpage_viewer_boot_js()
        self.assertIn("is-native-pdf", boot)
        self.assertIn("pdf-frame-wrap", boot)
        self.assertIn("removeAttribute('src')", boot)
        self.assertIn("/assets/pdf-inpage-viewer.js?v=20260823s", boot)
        self.assertNotIn("prefersNativePdf", boot)
        self.assertNotIn("narrowViewport", boot)
        self.assertEqual(boot, pdf_mobile_fallback_boot_js())

        css = pdf_inpage_viewer_css()
        self.assertIn("@media (max-width: 1024px)", css)
        self.assertIn("display: flex !important", css)
        self.assertIn(".pdf-frame-wrap iframe", css)
        self.assertIn("min-height: 850px", css)
        self.assertIn("height: 850px", css)
        self.assertIn("max-height: 850px", css)
        self.assertNotIn("85vh", css)
        self.assertIn("min-height: 450px", css)
        self.assertIn("height: 450px", css)
        self.assertIn("max-height: 450px", css)
        self.assertIn("overflow: auto", css)
        self.assertIn(".pdf-inpage-viewer", css)
        self.assertRegex(css, r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px")
        self.assertRegex(css, r"\.pdf-inpage-pages\s*\{[^}]*min-height:\s*850px")
        self.assertRegex(css, r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px")
        self.assertRegex(css, r"\.pdf-inpage-pages\s*\{[^}]*overflow:\s*auto")
        self.assertNotRegex(css, r"\.pdf-inpage-pages\s*\{[^}]*height:\s*auto")
        self.assertIn(".pdf-inpage-viewer", css)
        self.assertIn(".pdf-inpage-pages", css)
        self.assertNotIn("pdf-inpage-nav", css)
        self.assertEqual(css, pdf_mobile_fallback_css())

    def test_render_bulletin_viewer_shell_is_shared_canonical_design(self) -> None:
        """harvester.page_renderer.render_diocese_raphoe_page also calls this —
        this is the single source of truth for the bulletin viewer design."""
        html_output = render_bulletin_viewer_shell(
            page_title="Example Diocese Collated Bulletin",
            diocese_label="EXAMPLE",
            display_name="Example Diocese",
            headline="Example Collated Bulletin",
            meta_line="This week's bulletin — 19/05/2026.",
            back_href="../../index.html",
            back_label="← Back to home",
            pdf_href="https://example.com/example_mega_bulletin.pdf",
            pdf_download_href="https://example.com/example_mega_bulletin.pdf",
            pdf_standalone_href="https://example.com/example-pdf.html",
            ocr_standalone_href="https://example.com/example-ocr.html",
            ocr_fragment="<p>Sunday mass at 10am</p>",
            parish_section_heading="EXAMPLE Parishes with Working Bulletin Links",
            parish_links_html='<ul class="parish-grid"><li>Example Parish</li></ul>',
        )
        self.assertIn("Sunday mass at 10am", html_output)
        self.assertIn('href="/favicon.png"', html_output)
        self.assertIn('id="panel-pdf"', html_output)
        self.assertIn('id="panel-ocr"', html_output)
        self.assertIn("https://example.com/example-pdf.html", html_output)
        self.assertIn("https://example.com/example-ocr.html", html_output)
        self.assertIn("← Back to home", html_output)
        self.assertNotIn("callout-tip", html_output)
        self.assertNotIn("PRO TIP", html_output.upper())
        self.assertIn("min-height: 850px", html_output)
        self.assertIn("height: 850px", html_output)
        self.assertIn("max-height: 850px", html_output)
        self.assertRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*min-height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*max-height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*overflow:\s*auto",
        )
        self.assertRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*overflow-y:\s*auto",
        )
        self.assertNotRegex(
            html_output,
            r"#ocr-panel\s*\{[^}]*height:\s*auto",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-frame-wrap\s*\{[^}]*min-height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-inpage-pages\s*\{[^}]*min-height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-inpage-pages\s*\{[^}]*overflow:\s*auto",
        )
        self.assertNotRegex(
            html_output,
            r"\.pdf-inpage-pages\s*\{[^}]*height:\s*auto",
        )
        self.assertRegex(
            html_output,
            r"\.pdf-inpage-viewer,\s*\n\s*\.pdf-mobile-fallback\s*\{[^}]*min-height:\s*850px",
        )
        self.assertNotIn("85vh", html_output)
        self.assertIn("@media (max-width: 1024px)", html_output)
        self.assertIn("min-height: 450px", html_output)
        self.assertIn("height: 450px", html_output)
        self.assertIn("max-height: 450px", html_output)
        self.assertNotIn("parish-site-link", html_output)
        self.assertIn("mobile-jump", html_output)
        self.assertIn("Tap to go to plain text bulletin", html_output)
        self.assertIn('id="ocr-search"', html_output)
        self.assertIn("ocr-sticky-chrome", html_output)
        self.assertIn(".ocr-sticky-chrome.is-searching", html_output)
        self.assertIn("syncOcrSearchSticky", html_output)
        self.assertIn("position: sticky", html_output)
        self.assertIn('id="scroll-top-btn"', html_output)
        self.assertIn("Georgia", html_output)
        self.assertIn("pdf-inpage-viewer", html_output)
        self.assertIn("/assets/pdf-inpage-viewer.js?v=20260823s", html_output)
        self.assertIn("block: 'start'", html_output)
        self.assertNotIn("block: 'center'", html_output)
        self.assertIn("is-native-pdf", html_output)
        self.assertNotIn("pdf-inpage-prev", html_output)
        self.assertNotIn("pdf-inpage-next", html_output)
        self.assertNotIn("pdf-inpage-page-label", html_output)
        self.assertNotIn('id="pdf-inpage-viewer" hidden', html_output)

    def test_pdf_inpage_viewer_asset_streams_first_page(self) -> None:
        assets = Path(__file__).resolve().parent.parent / "docs" / "assets"
        viewer = assets / "pdf-inpage-viewer.js"
        self.assertTrue(viewer.is_file(), "docs/assets/pdf-inpage-viewer.js must exist for live pages")
        text = viewer.read_text(encoding="utf-8")
        self.assertIn("pdfjs", text.lower())
        self.assertIn("disableAutoFetch", text)
        self.assertIn("disableStream", text)
        self.assertIn("disableRange", text)
        self.assertIn("cdnjs.cloudflare.com/ajax/libs/pdf.js", text)
        self.assertNotIn("docs.google.com", text)
        self.assertIn("is-native-pdf", text)
        self.assertIn("stackAllPages", text)
        self.assertIn("numPages", text)
        self.assertIn("getAnnotations", text)
        self.assertIn("pdf-annot-link", text)
        self.assertIn('target = "_blank"', text)
        self.assertIn("noopener noreferrer", text)
        self.assertIn("min-height:850px", text.replace(" ", ""))
        self.assertIn("height:850px!important", text.replace(" ", ""))
        self.assertIn("max-height:850px!important", text.replace(" ", ""))
        self.assertIn("overflow:auto!important", text.replace(" ", ""))
        self.assertIn("overflow-y:auto!important", text.replace(" ", ""))
        self.assertIn("height:450px!important", text.replace(" ", ""))
        self.assertIn("max-height:450px!important", text.replace(" ", ""))
        self.assertNotIn("overflow:visible", text.replace(" ", ""))
        self.assertIn("!important", text)
        self.assertIn("#ocr-panel", text)
        self.assertIn("ocr-sticky-chrome", text)
        self.assertIn(".ocr-sticky-chrome.is-searching", text)
        self.assertIn("syncOcrSearchSticky", text)
        self.assertIn("position:sticky!important", text.replace(" ", ""))
        self.assertIn("scroll-top-btn", text)
        self.assertIn("ensureStickySearch", text)
        self.assertIn("ensureScrollTop", text)
        self.assertNotIn("85vh", text)
        self.assertIn(".pdf-inpage-pages", text)
        self.assertIn("Open PDF", text)
        self.assertIn("Download", text)
        self.assertNotIn("pdf-inpage-prev", text)
        self.assertNotIn("pdf-inpage-next", text)
        self.assertNotIn("pdf-inpage-page-label", text)
        self.assertNotIn('Page " + currentPage + " of', text)
        self.assertNotIn("narrowViewport", text)
        self.assertNotIn("prefersNativePdf", text)
        loader = assets / "pdf-mobile-fallback.js"
        self.assertTrue(loader.is_file())
        self.assertIn("pdf-inpage-viewer.js?v=20260823s", loader.read_text(encoding="utf-8"))

    def test_live_gortahork_ocr_has_mega_body_and_visible_850(self) -> None:
        """Frank 2026-08-21: parish slice must reuse mega OCR sentences; 850px on visible boxes."""
        docs = Path(__file__).resolve().parent.parent / "docs"
        html_live = (docs / "parishes" / "raphoe" / "gort-a-choirce.html").read_text(encoding="utf-8")
        self.assertIn("AIFRINN NA SEACHTAINE", html_live)
        self.assertIn("GORT A", html_live)
        self.assertIn("16ú Lúnasa 2026", html_live)
        self.assertIn("Donnchadh", html_live)
        self.assertRegex(html_live, r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px")
        self.assertRegex(html_live, r"\.pdf-inpage-pages\s*\{[^}]*min-height:\s*850px")
        self.assertRegex(html_live, r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px")
        self.assertRegex(html_live, r"\.pdf-inpage-pages\s*\{[^}]*overflow:\s*auto")
        self.assertNotRegex(html_live, r"\.pdf-inpage-pages\s*\{[^}]*height:\s*auto")
        self.assertRegex(html_live, r"#ocr-panel\s*\{[^}]*height:\s*850px")
        self.assertRegex(html_live, r"#ocr-panel\s*\{[^}]*min-height:\s*850px")
        self.assertRegex(html_live, r"#ocr-panel\s*\{[^}]*max-height:\s*850px")
        self.assertRegex(html_live, r"#ocr-panel\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(html_live, r"#ocr-panel\s*\{[^}]*overflow-y:\s*auto")
        self.assertNotRegex(html_live, r"#ocr-panel\s*\{[^}]*height:\s*auto")
        self.assertIn("ocr-sticky-chrome", html_live)
        self.assertIn('id="scroll-top-btn"', html_live)
        self.assertIn("/assets/pdf-inpage-viewer.js?v=20260822c", html_live)
        self.assertNotIn("85vh", html_live)
        self.assertIn("min-height: 450px", html_live)
        self.assertIn("height: 450px", html_live)
        self.assertIn("max-height: 450px", html_live)
        diocese = (docs / "dioceses" / "raphoe" / "index.html").read_text(encoding="utf-8")
        self.assertIn("AIFRINN NA SEACHTAINE", diocese)
        self.assertRegex(diocese, r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px")
        self.assertRegex(diocese, r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px")
        self.assertRegex(diocese, r"#ocr-panel\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(diocese, r"#ocr-panel\s*\{[^}]*overflow-y:\s*auto")
        self.assertNotRegex(diocese, r"#ocr-panel\s*\{[^}]*height:\s*auto")
        self.assertIn("ocr-sticky-chrome", diocese)
        self.assertIn(".ocr-sticky-chrome.is-searching", diocese)
        self.assertIn("syncOcrSearchSticky", diocese)
        self.assertIn('id="scroll-top-btn"', diocese)
        self.assertNotIn("85vh", diocese)

    def test_live_diocese_html_ships_inpage_viewer(self) -> None:
        """Generator-only changes are invisible on parishpress.ie — live HTML must include PDF.js."""
        docs = Path(__file__).resolve().parent.parent / "docs"
        for rel in (
            "dioceses/raphoe/index.html",
            "dioceses/derry/index.html",
            "dioceses/down-and-connor/index.html",
        ):
            html_live = (docs / rel).read_text(encoding="utf-8")
            self.assertIn("pdf-inpage-viewer", html_live, rel)
            self.assertIn("/assets/pdf-inpage-viewer.js?v=20260823s", html_live, rel)
            self.assertIn(".ocr-sticky-chrome.is-searching", html_live, rel)
            self.assertIn("syncOcrSearchSticky", html_live, rel)
            self.assertIn("data-pdf-src", html_live, rel)
            self.assertIn('src="/mega_pdf/', html_live, rel)
            self.assertNotIn("View this bulletin PDF", html_live, rel)
            self.assertRegex(
                html_live,
                r"\.pdf-frame-wrap\s*\{[^}]*min-height:\s*850px",
                msg=f"{rel} lost desktop PDF min-height 850px",
            )
            self.assertRegex(
                html_live,
                r"\.pdf-inpage-pages\s*\{[^}]*height:\s*850px",
                msg=f"{rel} PDF box must be locked height: 850px",
            )
            self.assertRegex(
                html_live,
                r"\.pdf-inpage-pages\s*\{[^}]*max-height:\s*850px",
                msg=f"{rel} PDF box must be max-height: 850px",
            )
            self.assertRegex(
                html_live,
                r"#ocr-panel\s*\{[^}]*min-height:\s*850px",
                msg=f"{rel} lost desktop OCR min-height 850px",
            )
            self.assertRegex(
                html_live,
                r"#ocr-panel\s*\{[^}]*height:\s*850px",
                msg=f"{rel} OCR box must be locked height: 850px",
            )
            self.assertRegex(
                html_live,
                r"#ocr-panel\s*\{[^}]*max-height:\s*850px",
                msg=f"{rel} OCR box must be max-height: 850px",
            )
            self.assertRegex(
                html_live,
                r"#ocr-panel\s*\{[^}]*overflow-y:\s*auto",
                msg=f"{rel} OCR box must scroll inside (overflow-y: auto)",
            )
            self.assertNotIn("85vh", html_live, rel)
            self.assertIn("ocr-parish-masthead", html_live, rel)
            self.assertIn("pdf-annot-link", html_live, rel)
            self.assertNotIn("PRO TIP", html_live.upper(), rel)
            self.assertNotIn("callout-tip", html_live, rel)
            self.assertNotIn("pdf-inpage-prev", html_live, rel)
            self.assertNotIn("pdf-inpage-next", html_live, rel)
            self.assertNotIn('class="pdf-inpage-page-label"', html_live, rel)
            self.assertNotIn('aria-label="Previous page"', html_live, rel)
            self.assertNotIn('aria-label="Next page"', html_live, rel)

    def test_render_ocr_standalone_page(self) -> None:
        config = DioceseConfig(
            key="test",
            display_name="Test Diocese",
            headline="TEST DIOCESE BIG BULLETIN",
            evidence_path=Path("unused.txt"),
            pdf_filename="test_mega_bulletin.pdf",
        )
        html_output = render_ocr_standalone_page(
            config=config,
            bulletin_date="2026-05-19",
            ocr_fragment="<p>Ar dheis Dé go raibh a anam</p>",
            viewer_href="test-2026-05-19.html",
        )
        self.assertIn("Text Bulletin", html_output)
        self.assertIn("Ar dheis Dé go raibh a anam", html_output)
        self.assertIn("Gaeilge", html_output)
        self.assertIn("19/05/2026", html_output)
        self.assertIn("ocr-sticky-chrome", html_output)
        self.assertIn(".ocr-sticky-chrome.is-searching", html_output)
        self.assertIn("syncOcrSearchSticky", html_output)
        self.assertIn("position: sticky", html_output)
        self.assertIn('id="scroll-top-btn"', html_output)
        self.assertIn("Back to top", html_output)

    def test_ocr_reading_styles_are_legible(self) -> None:
        """OCR pane must stay easy to read: soft paper, generous measure/line-height,
        no harsh white glare, and no horizontal overflow on phones."""
        from ocr.generate_bulletin_pages import (
            OCR_BASE_SIZE,
            OCR_INK,
            OCR_LINE_HEIGHT,
            OCR_MEASURE,
            OCR_PAPER,
            ocr_reading_css,
        )

        shared = ocr_reading_css("#ocr-panel")
        self.assertIn(OCR_PAPER, shared)
        self.assertIn(OCR_INK, shared)
        self.assertIn(f"line-height: {OCR_LINE_HEIGHT}", shared)
        self.assertIn(f"max-width: {OCR_MEASURE}", shared)
        self.assertIn("overflow-wrap: anywhere", shared)
        self.assertIn("72ch", OCR_MEASURE)
        self.assertEqual(OCR_LINE_HEIGHT, "1.65")
        self.assertEqual(OCR_BASE_SIZE, "1.125rem")
        # Soft cool stone — not pure white, not cream/terracotta cliché.
        self.assertNotEqual(OCR_PAPER.lower(), "#ffffff")
        self.assertNotEqual(OCR_PAPER.lower(), "#fff")

        viewer = render_bulletin_viewer_shell(
            page_title="Example Diocese Collated Bulletin",
            diocese_label="EXAMPLE",
            display_name="Example Diocese",
            headline="Example Collated Bulletin",
            meta_line="This week's bulletin — 19/05/2026.",
            back_href="../../index.html",
            back_label="← Back to home",
            pdf_href="https://example.com/example_mega_bulletin.pdf",
            pdf_download_href="https://example.com/example_mega_bulletin.pdf",
            pdf_standalone_href="https://example.com/example-pdf.html",
            ocr_standalone_href="https://example.com/example-ocr.html",
            ocr_fragment="<h2>Ardara</h2><p>Mass on Sunday at 11am.</p>",
            parish_section_heading="EXAMPLE Parishes with Working Bulletin Links",
            parish_links_html='<ul class="parish-grid"><li>Example Parish</li></ul>',
        )
        self.assertIn(f"line-height: {OCR_LINE_HEIGHT}", viewer)
        self.assertIn(f"max-width: {OCR_MEASURE}", viewer)
        self.assertIn(OCR_PAPER, viewer)
        self.assertIn("overflow-wrap: anywhere", viewer)
        self.assertIn('id="ocr-panel"', viewer)
        # Cramped legacy OCR body values must not return.
        self.assertNotRegex(viewer, r"#ocr-panel\s*\{[^}]*line-height:\s*1\.38")
        self.assertRegex(viewer, r"#ocr-panel p\s*\{[^}]*margin:\s*0 0 0\.9em")
        self.assertNotRegex(viewer, r"#ocr-panel p\s*\{[^}]*margin:\s*0 0 0\.35em")

        config = DioceseConfig(
            key="test",
            display_name="Test Diocese",
            headline="TEST DIOCESE BIG BULLETIN",
            evidence_path=Path("unused.txt"),
            pdf_filename="test_mega_bulletin.pdf",
        )
        standalone = render_ocr_standalone_page(
            config=config,
            bulletin_date="2026-05-19",
            ocr_fragment="<p>Sunday notices</p>",
            viewer_href="test-2026-05-19.html",
        )
        self.assertIn(f"line-height: {OCR_LINE_HEIGHT}", standalone)
        self.assertIn(OCR_PAPER, standalone)
        self.assertIn("overflow-wrap: anywhere", standalone)
        self.assertIn('class="ocr-body"', standalone)
        # Body/OCR reading measure — not the old cramped 1.35 body default.
        self.assertIn(f"line-height: {OCR_LINE_HEIGHT}", standalone)
        self.assertRegex(standalone, r"\.ocr-body\s*\{[^}]*line-height:\s*1\.65")
        self.assertNotRegex(standalone, r"body\s*\{[^}]*line-height:\s*1\.35")

        from ocr import convert_bulletin

        self.assertIn("line-height: 1.65", convert_bulletin.CSS)
        self.assertIn("min(72ch, 100%)", convert_bulletin.CSS)
        self.assertIn("#eef1f0", convert_bulletin.CSS)
        self.assertIn("overflow-wrap: anywhere", convert_bulletin.CSS)


    def test_az_parish_html_shows_failed_banner_when_no_markers_found(self) -> None:
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        # Garbage OCR text that names neither parish — simulates OCR failing
        # for the whole diocese (e.g. a broken/blank OCR run).
        html_output = build_az_parish_ocr_html("test", "asd asd asd 12345 !!!", parish_links)

        self.assertIn("ocr-failed-banner", html_output)
        self.assertIn("OCR failed this week", html_output)
        # Existing per-parish empty-row behaviour must still be present.
        self.assertIn("No searchable text available this week.", html_output)
        self.assertIn("Ardara Parish", html_output)
        self.assertIn("Bangor Parish", html_output)

    def test_prepare_ocr_fragment_is_continuous_no_accordion(self) -> None:
        """Frank: 'i absolutely hate the ocr the way its layed out the
        dropdown for each parish' — prepare_ocr_fragment must no longer
        rebuild the OCR text into collapsible per-parish <details> sections;
        it should read straight through, page by page, like the PDF."""
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        ocr_fragment = (
            '<p class="page-label">Page 1</p>'
            "<h2>Ardara Parish</h2>"
            "<p>Mass times this week: Saturday 6pm, Sunday 11am.</p>"
            "<h2>Bangor Parish</h2>"
            "<p>Confessions after Saturday evening Mass.</p>"
        )
        result = prepare_ocr_fragment("test", ocr_fragment, parish_links)

        self.assertNotIn("<details", result)
        self.assertNotIn("parish-block", result)
        self.assertNotIn("parish-head", result)
        self.assertIn("Page 1", result)
        self.assertIn("Ardara Parish", result)
        self.assertIn("Mass times this week", result)
        self.assertIn("Bangor Parish", result)
        # Original page order is preserved (Ardara's content appears before
        # Bangor's, exactly as extracted — not re-sorted A-Z into sections).
        self.assertLess(result.index("Mass times this week"), result.index("Confessions"))

    def test_prepare_ocr_fragment_flattens_legacy_accordion_markup(self) -> None:
        """Pages regenerated from already-published HTML (which may still
        carry the old collapsible <details class="parish-block"> markup from
        before Frank's round-2 fix) must come out flattened too — not just
        freshly-converted OCR."""
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        legacy_fragment = (
            '<details class="parish-block parish-even" id="parish-ardaraparish">\n'
            '  <summary class="parish-head">\n'
            '    <span class="parish-name">Ardara Parish</span>\n'
            '    <a class="parish-source" href="https://example.com/ardara" target="_blank" '
            'rel="noopener noreferrer" onclick="event.stopPropagation()">Newsletter</a>\n'
            "  </summary>\n"
            '  <div class="parish-body"><p>Mass times this week: Saturday 6pm.</p></div>\n'
            "</details>"
        )
        result = prepare_ocr_fragment("test", legacy_fragment, parish_links)

        self.assertNotIn("<details", result)
        self.assertNotIn("parish-block", result)
        self.assertNotIn("parish-head", result)
        self.assertNotIn("summary", result)
        self.assertIn("Ardara Parish", result)
        self.assertIn("Mass times this week", result)

    def test_prepare_ocr_fragment_keeps_failed_banner_when_no_parish_markers(self) -> None:
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        result = prepare_ocr_fragment("test", "<p>asd asd asd 12345 !!!</p>", parish_links)
        self.assertIn("ocr-failed-banner", result)
        self.assertIn("OCR failed this week", result)
        # Still no accordion — even the failure case is a continuous document.
        self.assertNotIn("<details", result)

    def test_az_parish_html_no_banner_when_some_parishes_have_content(self) -> None:
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        ocr_text = (
            "Ardara Parish\n"
            "https://example.com/ardara\n"
            "Mass times this week: Saturday 6pm, Sunday 11am.\n"
            "Confessions after Saturday evening Mass.\n"
            "Parish office open Monday to Friday, 10am-1pm.\n"
            "Contact Fr Smith on 087 123 4567 for anointing of the sick.\n"
        )
        html_output = build_az_parish_ocr_html("test", ocr_text, parish_links)

        self.assertNotIn("ocr-failed-banner", html_output)
        # Bangor genuinely has no content this week — its own empty row
        # must be preserved (item 4: don't touch short/empty real notices).
        self.assertIn("No searchable text available this week.", html_output)
        self.assertIn("Mass times this week", html_output)


if __name__ == "__main__":
    unittest.main()
