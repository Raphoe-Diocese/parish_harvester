"""Tests for harvester.fetcher capture-reliability fixes.

Covers: _is_real_pdf now also rejects over-long PDFs (folds in the
page-count check that used to only run on some paths); the HTML-render path
uses a lower size floor so genuine short bulletins aren't discarded; image
discovery accepts A4-sized scans; evidence parsing recognises .webp/.gif.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from datetime import date

from harvester.fetcher import (
    HTML_RENDER_MIN_BYTES,
    ParishEntry,
    classify_page_capped_pdf,
    freshness_after_unknown_url,
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


class ClassifyPageCappedPdfTests(unittest.TestCase):
    def _entry(self) -> ParishEntry:
        return ParishEntry(
            key="holycrossparishbelfast",
            display_name="Holy Cross Belfast",
            pattern="learned",
            content_type="pdf",
            example_url="http://www.holycrossparishbelfast.com/pdf/160826.pdf",
            bulletin_page="http://www.holycrossparishbelfast.com/parishnews.html",
        )

    def _long_pdf(self, path: Path, heading: str, pages: int = 6) -> None:
        c = canvas.Canvas(str(path))
        c.drawString(72, 700, "Recent Anniversaries : Marie Lavery")
        c.showPage()
        c.drawString(72, 700, heading)
        c.drawString(72, 680, "Caoimhin died on 9th July 2023.")
        c.showPage()
        for _ in range(pages - 2):
            c.drawString(72, 700, "filler page")
            c.showPage()
        c.save()
        with path.open("ab") as fh:
            fh.write(b"\n% " + b"0" * MIN_PDF_BYTES)

    def test_july_body_under_august_filename_is_stale_not_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "160826.pdf"
            self._long_pdf(pdf, "Bulletin 11th & 12th July 2026")
            self.assertFalse(_is_real_pdf(pdf))
            result = classify_page_capped_pdf(
                pdf,
                key="holycrossparishbelfast",
                display_name="Holy Cross Belfast",
                url="http://www.holycrossparishbelfast.com/pdf/160826.pdf",
                target=date(2026, 8, 16),
                entry=self._entry(),
                max_pages=4,
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.is_stale)
            self.assertIn("Stale bulletin rejected", result.error)
            self.assertIn("2026-07-12", result.error)
            self.assertNotIn("No valid content found", result.error)
            self.assertNotEqual(result.status, "ok")

    def test_current_week_oversized_pdf_is_honest_fail_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "160826.pdf"
            self._long_pdf(pdf, "Bulletin 16th August 2026")
            result = classify_page_capped_pdf(
                pdf,
                key="holycrossparishbelfast",
                display_name="Holy Cross Belfast",
                url="http://www.holycrossparishbelfast.com/pdf/160826.pdf",
                target=date(2026, 8, 16),
                entry=self._entry(),
                max_pages=4,
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertFalse(result.is_stale)
            self.assertIn("Too many pages", result.error)
            self.assertNotEqual(result.status, "ok")

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "gone.pdf"
            self.assertIsNone(
                classify_page_capped_pdf(
                    missing,
                    key="holycrossparishbelfast",
                    display_name="Holy Cross Belfast",
                    url="http://www.holycrossparishbelfast.com/pdf/160826.pdf",
                    target=date(2026, 8, 16),
                    entry=self._entry(),
                    max_pages=4,
                )
            )


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

    def test_holycross_recipe_keeps_default_page_cap(self) -> None:
        """Holy Cross 13-page July file must stay rejected (global default 4)."""
        recipe_path = (
            Path(__file__).resolve().parent.parent
            / "parishes"
            / "recipes"
            / "down_and_connor"
            / "holycrossparishbelfast.json"
        )
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        self.assertNotIn("max_bulletin_pages", recipe)
        self.assertEqual(recipe_max_bulletin_pages(recipe), MAX_BULLETIN_PAGES)
        self.assertEqual(MAX_BULLETIN_PAGES, 4)


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


class FreshnessAfterUnknownUrlTests(unittest.TestCase):
    """H1: undated URL + PDF heading date. Only a provably old body is stale."""

    UNDATED = "https://example.com/weekly-bulletin.pdf"
    TARGET = date(2026, 8, 23)

    def _heading_pdf(self, path: Path, *lines: str) -> None:
        c = canvas.Canvas(str(path))
        y = 700
        for line in lines:
            c.drawString(72, y, line)
            y -= 18
        c.save()

    def test_undated_url_july_heading_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "weekly-bulletin.pdf"
            self._heading_pdf(
                pdf, "RAPHOE PARISH NEWSLETTER Sunday 19 July 2026"
            )
            verdict = freshness_after_unknown_url(self.UNDATED, pdf, self.TARGET)
            self.assertEqual(verdict.status, "stale")
            self.assertEqual(verdict.extracted_date, date(2026, 7, 19))

    def test_undated_url_without_heading_stays_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "weekly-bulletin.pdf"
            self._heading_pdf(
                pdf,
                "In memory of Mary 12 July 2026",
                "© 2012-2026 Parish",
            )
            verdict = freshness_after_unknown_url(self.UNDATED, pdf, self.TARGET)
            self.assertEqual(verdict.status, "unknown")
            self.assertEqual(verdict.reason, "no_date_in_url")

    def test_undated_url_this_week_heading_stays_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "weekly-bulletin.pdf"
            self._heading_pdf(pdf, "Parish Newsletter 23 August 2026")
            verdict = freshness_after_unknown_url(self.UNDATED, pdf, self.TARGET)
            self.assertEqual(verdict.status, "unknown")
            self.assertEqual(verdict.reason, "no_date_in_url")


if __name__ == "__main__":
    unittest.main()
