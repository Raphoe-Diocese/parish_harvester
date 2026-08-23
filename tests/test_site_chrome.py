from __future__ import annotations

import unittest

from harvester.site_chrome import scroll_top_js


class ScrollTopInnerBoxTests(unittest.TestCase):
    def test_scroll_top_js_watches_inner_pdf_and_ocr_boxes(self) -> None:
        js = scroll_top_js()
        self.assertIn(".pdf-inpage-pages", js)
        self.assertIn("#ocr-panel", js)
        self.assertIn("maxInnerScroll", js)
        self.assertIn("capture: true", js)
        self.assertIn("innerBoxes", js)
        self.assertIn("el.scrollTop = 0", js)
        self.assertIn("window.scrollTo", js)
        self.assertIn("data-pp-bound", js)
        self.assertIn("data-pp-scroll-top", js)
        self.assertIn("inner-2", js)
        self.assertIn("DOMContentLoaded", js)
        self.assertIn("MutationObserver", js)
        self.assertIn("parishPressBindScrollTopBoxes", js)
        self.assertIn("wheel", js)
        # Must not only watch the window — that is why Frank's Raphoe
        # screenshot had no arrow after scrolling the locked 850px box.
        # Live HTML also runs this script before #scroll-top-btn exists.
        self.assertIn("y > 80 || maxInnerScroll() > 16", js)
        self.assertIn("document.createElement('button')", js)
        self.assertNotIn("if (!btn) return;", js)


if __name__ == "__main__":
    unittest.main()
