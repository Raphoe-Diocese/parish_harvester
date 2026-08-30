"""Gentle mega-PDF compress keeps a valid same-page-count file."""
from __future__ import annotations

import io
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from harvester.pdf_compress import compress_pdf_inplace


def _tiny_pdf(path: Path, pages: int = 2) -> None:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.setFont("Helvetica", 18)
        c.drawString(72, 720, f"Parish Press test page {i + 1}")
        c.showPage()
    c.save()
    path.write_bytes(buf.getvalue())


class PdfCompressTests(unittest.TestCase):
    def test_keeps_valid_pdf_and_page_count(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample_mega_bulletin.pdf"
            _tiny_pdf(path, pages=2)
            before = path.read_bytes()
            compress_pdf_inplace(path)
            after = path.read_bytes()
            self.assertTrue(after.startswith(b"%PDF-"))
            import fitz

            doc = fitz.open(stream=after, filetype="pdf")
            try:
                self.assertEqual(doc.page_count, 2)
            finally:
                doc.close()
            self.assertGreater(len(after), 32)
            # Tiny born-digital files may not shrink; never grow past original.
            self.assertLessEqual(len(after), len(before))

    def test_skips_missing_file(self) -> None:
        self.assertFalse(compress_pdf_inplace(Path("no-such-mega.pdf")))

    def test_ghostscript_cmd_downsamples_and_linearizes(self) -> None:
        from harvester.pdf_compress import _ghostscript_cmd

        cmd = " ".join(_ghostscript_cmd("gs", Path("in.pdf"), Path("out.pdf")))
        self.assertIn("-dFastWebView=true", cmd)
        self.assertIn("-dColorImageResolution=100", cmd)
        self.assertIn("-dGrayImageResolution=100", cmd)
