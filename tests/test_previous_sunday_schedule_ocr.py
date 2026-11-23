from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from harvester.bulletin_freshness import (
    FreshnessVerdict,
    _issue_schedule_covers_target_sunday,
    freshness_verdict_for_ok_result,
)


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
        assert _issue_schedule_covers_target_sunday(
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
        assert not _issue_schedule_covers_target_sunday(
            pdf, target, date(2026, 11, 15)
        )


def test_two_week_old_issue_is_not_accepted_by_schedule_ocr(tmp_path: Path) -> None:
    pdf = tmp_path / "scanned-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)

    with patch("ocr.sparse_page_ocr.ocr_pdf_page_lines") as ocr_page:
        assert not _issue_schedule_covers_target_sunday(
            pdf, target, date(2026, 11, 8)
        )
        ocr_page.assert_not_called()

def test_bulletin_dated_at_week_end_can_prove_target_sunday_schedule(tmp_path: Path) -> None:
    pdf = tmp_path / "weekly-range-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)
    weekly_schedule = ["Kincasslagh Parish Newsletter, 20th - 28th November",
                       "Sun 22nd 10.00am Mass"]

    with patch("harvester.bulletin_freshness.read_pdf_page_texts", return_value=weekly_schedule):
        assert _issue_schedule_covers_target_sunday(
            pdf, target, date(2026, 11, 28)
        )


def test_week_end_date_without_target_schedule_stays_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "weekly-range-bulletin.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)

    with patch("harvester.bulletin_freshness.read_pdf_page_texts", return_value=["Newsletter 20-28 November", "Mass 10.00am"]):
        assert not _issue_schedule_covers_target_sunday(
            pdf, target, date(2026, 11, 28)
        )

def test_future_dated_weekly_issue_is_accepted_only_when_schedule_covers_target(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "kincasslagh-weekly-range.pdf"
    pdf.write_bytes(b"%PDF-test")
    target = date(2026, 11, 22)
    result = SimpleNamespace(
        url="https://example.org/Newsletter-20th-28th-November.pdf",
        file_path=pdf,
        key="",
    )
    with (
        patch(
            "harvester.bulletin_freshness.check_bulletin_freshness",
            return_value=FreshnessVerdict(
                status="stale",
                extracted_date=date(2026, 11, 28),
                reason="date_ahead_of_target",
            ),
        ),
        patch("harvester.bulletin_freshness._parish_status_row", return_value={}),
        patch("harvester.bulletin_freshness._pdf_file_bytes", return_value=9),
        patch(
            "harvester.bulletin_freshness.saved_bulletin_issue_date",
            return_value=(date(2026, 11, 28), "front_page"),
        ),
        patch(
            "harvester.bulletin_freshness.pdf_date_before_harvest_week",
            return_value=None,
        ),
        patch(
            "harvester.bulletin_freshness.read_pdf_page_texts",
            return_value=["Kincasslagh Parish Newsletter 20th–28th November", "Sun 22nd 10.00am Mass"],
        ),
    ):
        verdict = freshness_verdict_for_ok_result(result, target)

    assert verdict.status == "fresh"
    assert verdict.reason == "printed_weekly_schedule_covers_target"
    assert verdict.extracted_date == date(2026, 11, 28)
