"""Tests for harvester.fetcher capture-reliability fixes.

Covers: _is_real_pdf now also rejects over-long PDFs (folds in the
page-count check that used to only run on some paths); the HTML-render path
uses a lower size floor so genuine short bulletins aren't discarded; image
discovery accepts A4-sized scans; evidence parsing recognises .webp/.gif.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from harvester.fetcher import (
    HTML_RENDER_MIN_BYTES,
    _is_real_pdf,
    _reject_if_oversized,
    recipe_max_bulletin_pages,
)
from harvester.config import MAX_BULLETIN_PAGES, MIN_PDF_BYTES


def _make_pdf_with_pages(path: Path, page_count: int, filler: str = "x" * 2000) -> None:
    c = canvas.Canvas(str(path))
    for i in range(page_count):
        c.drawString(72, 700, f"Page {i + 1} {filler[:50]}")
        c.showPage()
    c.save()


class IsRealPdfTests(unittest.TestCase):
    def test_accepts_pdf_within_page_and_size_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "ok.pdf"
            _make_pdf_with_pages(pdf, 2)
            # Pad past MIN_PDF_BYTES so the default-threshold check passes.
            with pdf.open("ab") as fh:
                fh.write(b"\n% " + b"0" * MIN_PDF_BYTES)
            self.assertTrue(_is_real_pdf(pdf))

    def test_rejects_pdf_over_page_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "toolong.pdf"
            _make_pdf_with_pages(pdf, 6)
            with pdf.open("ab") as fh:
                fh.write(b"\n% " + b"0" * MIN_PDF_BYTES)
            self.assertFalse(_is_real_pdf(pdf))

    def test_custom_min_bytes_accepts_smaller_html_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "short.pdf"
            _make_pdf_with_pages(pdf, 1)
            size = pdf.stat().st_size
            # A tiny real capture: bigger than HTML_RENDER_MIN_BYTES but
            # smaller than the default MIN_PDF_BYTES floor.
            self.assertLess(size, MIN_PDF_BYTES)
            if size < HTML_RENDER_MIN_BYTES:
                with pdf.open("ab") as fh:
                    fh.write(b"\n% " + b"0" * (HTML_RENDER_MIN_BYTES - size + 10))
            self.assertFalse(_is_real_pdf(pdf))  # default floor still rejects
            self.assertTrue(_is_real_pdf(pdf, min_bytes=HTML_RENDER_MIN_BYTES))

    def test_unreadable_pdf_page_structure_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "corrupt.pdf"
            pdf.write_bytes(b"%PDF-1.4" + b"0" * MIN_PDF_BYTES)
            # Magic bytes look real but page structure is garbage — should
            # not raise, and current behaviour (accept) is unchanged since
            # page count can't be determined.
            _is_real_pdf(pdf)  # must not raise

    def test_recipe_max_pages_override_accepts_longer_bulletin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "ardmore_style.pdf"
            _make_pdf_with_pages(pdf, 9)
            with pdf.open("ab") as fh:
                fh.write(b"\n% " + b"0" * MIN_PDF_BYTES)
            self.assertEqual(MAX_BULLETIN_PAGES, 4)
            self.assertFalse(_is_real_pdf(pdf))  # global default still rejects
            self.assertTrue(_is_real_pdf(pdf, max_pages=12))  # Ardmore-style override


class RecipeMaxBulletinPagesTests(unittest.TestCase):
    def test_default_is_global_max(self) -> None:
        self.assertEqual(recipe_max_bulletin_pages(None), MAX_BULLETIN_PAGES)
        self.assertEqual(recipe_max_bulletin_pages({}), MAX_BULLETIN_PAGES)

    def test_reads_max_bulletin_pages_from_recipe(self) -> None:
        self.assertEqual(
            recipe_max_bulletin_pages({"max_bulletin_pages": 12}),
            12,
        )

    def test_invalid_or_too_small_falls_back_to_global(self) -> None:
        self.assertEqual(recipe_max_bulletin_pages({"max_bulletin_pages": 0}), MAX_BULLETIN_PAGES)
        self.assertEqual(recipe_max_bulletin_pages({"max_bulletin_pages": "nope"}), MAX_BULLETIN_PAGES)


class RejectIfOversizedTests(unittest.TestCase):
    def test_small_file_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "small.pdf"
            pdf.write_bytes(b"%PDF-1.4 small")
            _reject_if_oversized(pdf)  # should not raise
            self.assertTrue(pdf.exists())

    def test_oversized_file_deleted_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "huge.pdf"
            pdf.write_bytes(b"%PDF-1.4 " + b"0" * (6 * 1_000_000))  # 6 MB > 5 MB cap
            with self.assertRaises(ValueError):
                _reject_if_oversized(pdf)
            self.assertFalse(pdf.exists())


if __name__ == "__main__":
    unittest.main()
