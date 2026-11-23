from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from harvester.bulletin_freshness import _previous_sunday_issue_covers_target_sunday


def test_previous_sunday_scanned_bulletin_can_prove_current_sunday_schedule(tmp_path: Path) -> None:
    pdf = tmp_path / "scanned-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)
    scanned_schedule = ["Sunday 22 November 2026", "Mass 11.00am"]

    with (
        patch("harvester.bulletin_freshness.read_pdf_page_texts", return_value=["", ""]),
        patch("shutil.which", return_value="/usr/bin/tesseract"),
        patch("ocr.sparse_page_ocr.ocr_pdf_page_lines", side_effect=[scanned_schedule, []]),
    ):
        assert _previous_sunday_issue_covers_target_sunday(
            pdf, target, date(2026, 11, 15)
        )


def test_previous_sunday_scan_without_target_schedule_stays_stale(tmp_path: Path) -> None:
    pdf = tmp_path / "scanned-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)

    with (
        patch("harvester.bulletin_freshness.read_pdf_page_texts", return_value=["", ""]),
        patch("shutil.which", return_value="/usr/bin/tesseract"),
        patch("ocr.sparse_page_ocr.ocr_pdf_page_lines", return_value=["Sunday 15 November 2026"]),
    ):
        assert not _previous_sunday_issue_covers_target_sunday(
            pdf, target, date(2026, 11, 15)
        )


def test_two_week_old_issue_is_not_accepted_by_schedule_ocr(tmp_path: Path) -> None:
    pdf = tmp_path / "scanned-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)

    with patch("ocr.sparse_page_ocr.ocr_pdf_page_lines") as ocr_page:
        assert not _previous_sunday_issue_covers_target_sunday(
            pdf, target, date(2026, 11, 8)
        )
        ocr_page.assert_not_called()
