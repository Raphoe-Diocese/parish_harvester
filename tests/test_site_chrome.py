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
        self.assertIn("scrollTop = 0", js)
        self.assertIn("window.scrollTo", js)
        self.assertIn("data-pp-bound", js)
        # Must not only watch the window — that is why Frank's Raphoe
        # screenshot had no arrow after scrolling the locked 850px box.
        self.assertIn("y > 240 || maxInnerScroll() > 80", js)


if __name__ == "__main__":
    unittest.main()
