"""Tests for harvester.report — reject error/security pages saved as "PDFs".

These must never trigger on PDFs with no extractable text at all, because
scanned/photographed bulletin PDFs (image_stack recipes) legitimately have no
text layer and are a real, working capture method — not junk.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from reportlab.pdfgen import canvas

from harvester.report import _pdf_error_page_reason, _result_to_report_entry, generate_report


def _make_text_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, text)
    c.save()


def _make_blank_pdf(path: Path) -> None:
    # A page with no text at all — stands in for a scanned/image-only bulletin.
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()


def _fake_result(key: str, file_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        display_name=key.title(),
        url="https://example.com/" + key,
        status="ok",
        file_path=file_path,
        file_type="pdf",
        is_stale=False,
        is_fallback=False,
        error=None,
        diagnosis=None,
    )


class PdfErrorPageTests(unittest.TestCase):
    def test_error_page_text_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "bad.pdf"
            _make_text_pdf(pdf, "403 Forbidden - Access Denied")
            self.assertIsNotNone(_pdf_error_page_reason(pdf))

    def test_real_short_bulletin_text_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "good.pdf"
            _make_text_pdf(pdf, "St Mary's Parish - Mass times Saturday 6pm, Sunday 11am")
            self.assertIsNone(_pdf_error_page_reason(pdf))

    def test_blank_no_text_pdf_is_not_flagged(self) -> None:
        # Proves scanned/image-only bulletins (no text layer) are never
        # rejected by this check.
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "scanned.pdf"
            _make_blank_pdf(pdf)
            self.assertIsNone(_pdf_error_page_reason(pdf))

    def test_unreadable_file_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "junk.pdf"
            pdf.write_bytes(b"%PDF-1.4 not a real pdf")
            self.assertIsNone(_pdf_error_page_reason(pdf))

    def test_result_to_report_entry_routes_error_page_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf = tmp_path / "captcha.pdf"
            _make_text_pdf(pdf, "Please complete the security check to continue")
            result = _fake_result("someparish", pdf)

            bucket, entry = _result_to_report_entry(result, tmp_path / "current")

            self.assertEqual(bucket, "failed")
            self.assertIn("error/security page", entry.get("error", ""))

    def test_generate_report_routes_error_page_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_dir = tmp_path / "raw"
            raw_dir.mkdir()
            current_dir = tmp_path / "current"
            pdf = raw_dir / "someparish.pdf"
            _make_text_pdf(pdf, "404 Not Found")
            result = _fake_result("someparish", pdf)

            report = generate_report(
                [result],
                raw_dir,
                current_dir,
                tmp_path / "report.json",
                tmp_path / "report.txt",
                date(2026, 7, 26),
            )

            self.assertEqual(report["summary"]["downloaded"], 0)
            self.assertEqual(report["summary"]["failed"], 1)
            self.assertFalse((current_dir / "someparish.pdf").exists())


if __name__ == "__main__":
    unittest.main()
