from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.pdf_compress import compress_pdf_inplace


class PdfCompressTests(unittest.TestCase):
    def test_missing_file_returns_false(self) -> None:
        self.assertFalse(compress_pdf_inplace("/tmp/does-not-exist-pp-mega.pdf"))

    def test_two_page_reportlab_stays_valid(self) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen.canvas import Canvas

        import fitz

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "two.pdf"
            canvas = Canvas(str(path), pagesize=A4)
            canvas.drawString(72, 720, "Page one")
            canvas.showPage()
            canvas.drawString(72, 720, "Page two")
            canvas.save()
            before = path.stat().st_size
            compress_pdf_inplace(path)
            self.assertTrue(path.read_bytes()[:5] == b"%PDF-")
            doc = fitz.open(path)
            try:
                self.assertEqual(doc.page_count, 2)
            finally:
                doc.close()
            self.assertLessEqual(path.stat().st_size, before)
