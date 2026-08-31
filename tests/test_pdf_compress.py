from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.pdf_compress import compress_pdf_inplace, first_page_preview_path, write_first_page_preview


class PdfCompressTests(unittest.TestCase):
    def test_ghostscript_cmd_downsamples_and_linearizes(self) -> None:
        from harvester.pdf_compress import _ghostscript_cmd

        cmd = " ".join(_ghostscript_cmd("gs", Path("in.pdf"), Path("out.pdf")))
        self.assertIn("-dFastWebView=true", cmd)
        self.assertIn("-dColorImageResolution=100", cmd)
        self.assertIn("-dGrayImageResolution=100", cmd)

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
            p1 = write_first_page_preview(path)
            self.assertIsNotNone(p1)
            self.assertEqual(p1, first_page_preview_path(path))
            self.assertTrue(p1.read_bytes()[:3] == b"\xff\xd8\xff")
            self.assertGreater(p1.stat().st_size, 32)
            self.assertLess(p1.stat().st_size, 200_000)
