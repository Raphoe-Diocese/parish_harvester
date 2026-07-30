"""Tests for harvester.replay._verify_bulletin_pdf — the HTML/print-to-PDF
recipe path must reject over-long captures the same way direct downloads do
(harvester.fetcher._verify_bulletin_pdf)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from harvester.replay import _verify_bulletin_pdf


def _make_pdf_with_pages(path: Path, page_count: int) -> None:
    c = canvas.Canvas(str(path))
    for i in range(page_count):
        c.drawString(72, 700, f"Page {i + 1}")
        c.showPage()
    c.save()


class VerifyBulletinPdfTests(unittest.TestCase):
    def test_accepts_pdf_within_page_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "ok.pdf"
            _make_pdf_with_pages(pdf, 2)
            _verify_bulletin_pdf(pdf)  # should not raise
            self.assertTrue(pdf.exists())

    def test_rejects_and_deletes_pdf_over_page_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "toolong.pdf"
            _make_pdf_with_pages(pdf, 6)  # MAX_BULLETIN_PAGES is 4
            with self.assertRaises(ValueError):
                _verify_bulletin_pdf(pdf)
            self.assertFalse(pdf.exists())

    def test_unreadable_file_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "junk.pdf"
            pdf.write_bytes(b"not a real pdf")
            _verify_bulletin_pdf(pdf)  # should not raise — left to other checks
            self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
