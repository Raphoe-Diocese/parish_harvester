from __future__ import annotations

import unittest

from ocr.parish_splitter import split_ocr_by_parish, split_ocr_html_by_parish


class SplitOcrByParishTests(unittest.TestCase):
    def test_split_ocr_by_parish_basic(self) -> None:
        text = "Ardara Parish\nSome ardara content.\n\nAnnagry\nhttp://annagry.example\nMass at 10am.\n"
        entries = [("ardara", "Ardara"), ("annagryparish", "Annagry")]
        chunks = split_ocr_by_parish(text, entries)
        self.assertIn("Some ardara content", chunks["ardara"])
        self.assertIn("Mass at 10am", chunks["annagryparish"])

    def test_split_ocr_by_parish_no_markers_returns_empty(self) -> None:
        entries = [("ardara", "Ardara")]
        chunks = split_ocr_by_parish("Nothing relevant here at all.", entries)
        self.assertEqual(chunks, {"ardara": ""})


_FRAGMENT = """
<p class="page-label">Page 1</p>
<h2 class="b-title">Index</h2>
<p>Welcome to the diocese bulletin.</p>
<hr>
<p class="page-label">Page 2</p>
<p>Ardara Parish<br>
http://ardara.ie</p>
<h3 class="b-head">Mass Times</h3>
<table class="b-table"><tr><th>Day</th></tr><tr><td>Sunday 10am</td></tr></table>
<p>Recently deceased: John Smith.</p>
<hr>
<p class="page-label">Page 3</p>
<p>Annagry<br>
https://annagryparish.ie/newsletter-2/</p>
<p>Mass at 11am.</p>
<hr>
<p class="page-label">Page 4</p>
<p>Annagry<br>
https://annagryparish.ie/newsletter-2/</p>
<p>Second page for annagry.</p>
"""


class SplitOcrHtmlByParishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = [("ardara", "Ardara"), ("annagryparish", "Annagry")]

    def test_finds_page_aligned_ranges(self) -> None:
        chunks = split_ocr_html_by_parish(_FRAGMENT, self.entries)
        ardara = chunks["ardara"]
        annagry = chunks["annagryparish"]

        self.assertEqual((ardara.start_page, ardara.end_page), (2, 2))
        self.assertEqual((annagry.start_page, annagry.end_page), (3, 4))

    def test_chunk_html_does_not_leak_into_neighbour(self) -> None:
        chunks = split_ocr_html_by_parish(_FRAGMENT, self.entries)
        ardara_html = chunks["ardara"].html
        annagry_html = chunks["annagryparish"].html

        self.assertIn("Recently deceased", ardara_html)
        self.assertIn("Mass Times", ardara_html)
        self.assertNotIn("Second page for annagry", ardara_html)
        self.assertNotIn("Recently deceased", annagry_html)
        self.assertIn("Second page for annagry", annagry_html)

    def test_no_markers_returns_empty_with_none_pages(self) -> None:
        chunks = split_ocr_html_by_parish("<p>Nothing relevant here.</p>", self.entries)
        for chunk in chunks.values():
            self.assertEqual(chunk.html, "")
            self.assertIsNone(chunk.start_page)
            self.assertIsNone(chunk.end_page)

    def test_empty_fragment_returns_empty_chunks(self) -> None:
        chunks = split_ocr_html_by_parish("", self.entries)
        self.assertEqual(set(chunks), {"ardara", "annagryparish"})
        self.assertTrue(all(c.html == "" for c in chunks.values()))

    def test_live_shaped_banner_same_paragraph_newline_no_br(self) -> None:
        """Real published OCR puts Name + URL in one <p> with a raw newline."""
        fragment = """
<p class="page-label">Page 1</p>
<p>Annagry
<a href="https://annagryparish.ie/newsletter-2/">https://annagryparish.ie/newsletter-2/</a></p>
<hr>
<p class="page-label">Page 2</p>
<p>Weekend Mass Times
Recent DeathsArdara
<a href="http://ardara.ie/news/">http://ardara.ie/news/</a></p>
<p>Sunday mass at 10am.</p>
"""
        chunks = split_ocr_html_by_parish(fragment, self.entries)
        self.assertEqual((chunks["annagryparish"].start_page, chunks["annagryparish"].end_page), (1, 1))
        self.assertEqual((chunks["ardara"].start_page, chunks["ardara"].end_page), (2, 2))
        self.assertIn("Sunday mass at 10am", chunks["ardara"].html)
        self.assertNotIn("Sunday mass at 10am", chunks["annagryparish"].html)


class SplitOcrHtmlByPageRangesTests(unittest.TestCase):
    def test_slices_by_authoritative_page_index(self) -> None:
        from ocr.parish_splitter import split_ocr_html_by_page_ranges

        chunks = split_ocr_html_by_page_ranges(_FRAGMENT, {"ardara": (2, 2), "annagryparish": (3, 4)})
        self.assertEqual((chunks["ardara"].start_page, chunks["ardara"].end_page), (2, 2))
        self.assertIn("Recently deceased", chunks["ardara"].html)
        self.assertIn("Second page for annagry", chunks["annagryparish"].html)
        self.assertNotIn("Recently deceased", chunks["annagryparish"].html)


if __name__ == "__main__":
    unittest.main()
