from __future__ import annotations

import unittest

from ocr.sparse_page_ocr import (
    join_ocr_html_pages,
    ocr_lines_look_usable,
    page_html_is_sparse,
    prefer_embedded_pages_in_ocr_html,
    split_ocr_html_pages,
)


class SparsePageOcrHtmlTests(unittest.TestCase):
    def test_split_and_join_plain_page_markers(self) -> None:
        fragment = (
            "<p>Page 14</p>\n"
            "<p>Gortahork</p>\n"
            "<hr>\n"
            "<p>Page 15</p>\n"
            "<p>Inver mass times.</p>"
        )
        pages = split_ocr_html_pages(fragment)
        self.assertEqual([num for num, _ in pages], [14, 15])
        self.assertTrue(page_html_is_sparse(pages[0][1]))
        self.assertFalse(page_html_is_sparse(pages[1][1] + " extra body " * 20))
        joined = join_ocr_html_pages(pages)
        self.assertIn('class="page-label"', joined)
        self.assertIn("Page 14", joined)
        self.assertIn("Page 15", joined)

    def test_irish_body_is_not_sparse(self) -> None:
        body = (
            "<p>AIFRINN NA SEACHTAINE<br>\n"
            "16ú Lúnasa 2026<br>\n"
            "An tAth. Donnchadh Ó Baoill, Pobal Chríost Rí, Gort a' Choirce<br>\n"
            "Nora O'Donnell, An Bhealtaine / An Chlochán Liath<br>\n"
            "Eamon Mc Ginley, Inis Bó Finne / An Fál Carrach<br>\n"
            "Tógadh €1,530 an tseachtain s'chuaigh thart. Buíochas don phobal.</p>"
        )
        self.assertFalse(page_html_is_sparse(body))
        self.assertFalse(
            page_html_is_sparse(
                "<p>Weekend Mass Times<br>\nSaturday Vigil Kilclooney 6.00pm Ardara 7.30pm</p>"
            )
        )
        irish = [
            "POBAL CHRÍOST RÍ GORT A’ CHOIRCE AIFRINN NA SEACHTAINE",
            "16ú Lúnasa 2026 An tAth. Donnchadh Ó Baoill paróiste",
            "Nora O'Donnell, An Bhealtaine agus Eamon Mc Ginley Inis Bó Finne",
            "Tógadh €1,530 an tseachtain s'chuaigh thart. Buíochas don phobal uile.",
            "Seo mar a deir an Tiarna: Coinnígí an ceart, cleachtaígí an fhíréanacht.",
        ]
        self.assertTrue(ocr_lines_look_usable(irish))
        self.assertFalse(ocr_lines_look_usable(["H", "q", "‘", ". aN wy ?", "at i Réalt n"]))

    def test_prefer_embedded_html_restores_dropped_line(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from reportlab.pdfgen import canvas

        lines = [
            "Ramoan Parish Ballycastle weekend bulletin",
            "Coffee morning Saturday 22nd August in the crypt.",
            "Church Car Park will be closed immediately after 12noon Mass on Sunday 23rd August.",
            "Lough Derg retreats August 18th, 22nd, 23rd please book in the sacristy.",
            "Weekend Mass Times Saturday Vigil 6.30pm Sunday 10.00am and 12.00noon.",
        ]
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 760
        for line in lines:
            c.drawString(72, y, line)
            y -= 14
        c.showPage()
        c.save()
        vision_html = (
            '<p class="page-label">Page 1</p>\n'
            "<p>Coffee morning Saturday 2nd August in the crypt.</p>"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "slice.pdf"
            pdf_path.write_bytes(buf.getvalue())
            out = prefer_embedded_pages_in_ocr_html(vision_html, pdf_path)
        self.assertIn("Church Car Park will be closed", out)
        self.assertIn("22nd August", out)
        self.assertNotIn("Saturday 2nd August", out)


if __name__ == "__main__":
    unittest.main()
