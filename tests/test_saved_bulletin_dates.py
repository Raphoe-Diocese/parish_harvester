"""Blank saved bulletins get a date only when one of the real ways finds it."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from reportlab.pdfgen import canvas

from harvester.bulletin_freshness import (
    extract_bulletin_date,
    freshness_verdict_for_ok_result,
    heading_date_in_pdf,
    issue_date_from_pages,
    saved_bulletin_issue_date,
)
from harvester.report import _bulletin_date_fields
from scripts.date_saved_bulletins import apply_saved_dates

SUNDAY = date(2026, 11, 8)


def _pdf(path: Path, *page_lines: list[str]) -> None:
    pen = canvas.Canvas(str(path))
    for lines in page_lines:
        y = 800
        for line in lines:
            pen.drawString(72, y, line)
            y -= 16
        pen.showPage()
    pen.save()


def test_later_sunday_line_without_the_word_newsletter() -> None:
    found, way = issue_date_from_pages(
        [
            "Parish of Example\nMass at 11am\nConfessions Saturday",
            "Sunday 8th November 2026",
        ],
        SUNDAY,
    )
    assert found == SUNDAY
    assert way == "later_page"


def test_october_front_page_is_not_replaced_by_a_later_mass_time() -> None:
    found, way = issue_date_from_pages(
        [
            "Parish of Trim and Boardsmill\n4 – 10 October 2026",
            "Sunday 8 November 10am: Children for First Communion",
        ],
        SUNDAY,
    )
    assert found is None
    assert found != SUNDAY
    assert way == "front_outside"
    # The same Mass line on its own is still not this Sunday.
    alone, alone_way = issue_date_from_pages(
        ["Sunday 8 November 10am"],
        SUNDAY,
    )
    assert alone is None
    assert alone_way == ""


def test_a_later_full_sunday_does_not_override_an_october_front_page() -> None:
    found, _way = issue_date_from_pages(
        [
            "4 – 10 October 2026",
            "Sunday 8th November 2026",
        ],
        SUNDAY,
    )
    assert found is None


def test_death_date_is_not_the_issue_date() -> None:
    found, way = issue_date_from_pages(
        ["John died on 9th July 2023."],
        SUNDAY,
    )
    assert found is None
    assert way == ""


def test_thirty_second_sunday_and_2026_is_this_sunday() -> None:
    found, way = issue_date_from_pages(
        ["Thirty-Second Sunday in Ordinary Time\nParish of Example\n2026"],
        SUNDAY,
    )
    assert found == SUNDAY
    assert way == "liturgical"


def test_thirty_second_sunday_with_no_year_stays_blank() -> None:
    found, _way = issue_date_from_pages(
        ["Thirty-Second Sunday in Ordinary Time"],
        SUNDAY,
    )
    assert found is None
    bare, _bare_way = issue_date_from_pages(
        ["Thirty-Second Sunday\n32nd Sunday"],
        SUNDAY,
    )
    assert bare is None


def test_thirty_second_sunday_in_another_year_is_not_this_sunday() -> None:
    found, _way = issue_date_from_pages(
        ["Thirty-Second Sunday in Ordinary Time\n2025"],
        SUNDAY,
    )
    assert found is None
    assert found != SUNDAY


def test_row_url_fills_a_blank_pdf_when_the_parser_reads_this_week(tmp_path: Path) -> None:
    pdf = tmp_path / "example.pdf"
    _pdf(pdf, [])
    url = "https://parish.ie/files/Newsletter_20261108.png"
    found = heading_date_in_pdf(pdf, target=SUNDAY, url=url)
    assert found == SUNDAY


def test_09_11_08_filename_is_not_this_sunday(tmp_path: Path) -> None:
    assert extract_bulletin_date("https://parish.ie/09-11-08.pdf") == date(2009, 11, 8)
    assert extract_bulletin_date("https://parish.ie/11.08.26.pdf") == date(2026, 8, 11)
    pdf = tmp_path / "old.pdf"
    _pdf(pdf, [])
    assert heading_date_in_pdf(
        pdf, target=SUNDAY, url="https://parish.ie/09-11-08.pdf"
    ) is None
    assert heading_date_in_pdf(
        pdf, target=SUNDAY, url="https://parish.ie/11.08.26.pdf"
    ) is None


def test_later_page_is_read_from_the_pdf_itself(tmp_path: Path) -> None:
    pdf = tmp_path / "later.pdf"
    _pdf(
        pdf,
        ["Parish of Example", "No date on this page"],
        ["Sunday 8th November 2026"],
    )
    assert heading_date_in_pdf(pdf, target=SUNDAY) == SUNDAY


def test_ocr_text_counts_only_inside_this_week(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "scan.pdf"
    _pdf(pdf, [])
    monkeypatch.setattr(
        "harvester.bulletin_freshness._ocr_first_page_text",
        lambda path: "Sunday 8th November 2026",
    )
    found, way = saved_bulletin_issue_date(pdf, target=SUNDAY)
    assert found == SUNDAY
    assert way == "ocr"
    monkeypatch.setattr(
        "harvester.bulletin_freshness._ocr_first_page_text",
        lambda path: "4 – 10 October 2026\nSunday 8 November 10am",
    )
    assert saved_bulletin_issue_date(pdf, target=SUNDAY)[0] is None


def test_missing_tesseract_leaves_a_photo_blank(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "scan.pdf"
    _pdf(pdf, [])
    monkeypatch.setattr("shutil.which", lambda _name: None)

    def _boom(*_args, **_kwargs):
        raise AssertionError("OCR must not run without tesseract")

    monkeypatch.setattr("ocr.sparse_page_ocr.ocr_pdf_page_lines", _boom)
    assert saved_bulletin_issue_date(pdf, target=SUNDAY)[0] is None


def test_script_writes_only_a_date_inside_the_week(tmp_path: Path) -> None:
    bulletins = tmp_path / "Bulletins"
    bulletins.mkdir()
    _pdf(bulletins / "good.pdf", [])
    _pdf(bulletins / "old.pdf", [])
    _pdf(bulletins / "words.pdf", ["Notices"], ["Sunday 8th November 2026"])
    status = {
        "target_date": "2026-11-08",
        "parishes": {
            "good": {
                "outcome": "ok",
                "bulletin_date": None,
                "url": "https://parish.ie/files/Newsletter_20261108.png",
            },
            "old": {
                "outcome": "ok",
                "bulletin_date": None,
                "url": "https://parish.ie/09-11-08.pdf",
            },
            "words": {
                "outcome": "ok",
                "bulletin_date": None,
                "url": "",
            },
            "kept": {
                "outcome": "ok",
                "bulletin_date": "2026-11-01",
                "bulletin_date_uk": "01/11/2026",
                "url": "https://parish.ie/files/Newsletter_20261108.png",
            },
            "failed": {
                "outcome": "failed",
                "bulletin_date": None,
                "url": "https://parish.ie/files/Newsletter_20261108.png",
            },
        },
    }
    path = tmp_path / "parish_status.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    summary = apply_saved_dates(path, bulletins)
    assert summary["dated"] == 2
    assert summary["on_sunday"] == 2
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["parishes"]["good"]["bulletin_date"] == "2026-11-08"
    assert saved["parishes"]["good"]["bulletin_date_uk"] == "08/11/2026"
    assert saved["parishes"]["words"]["bulletin_date"] == "2026-11-08"
    assert saved["parishes"]["old"]["bulletin_date"] is None
    assert saved["parishes"]["kept"]["bulletin_date"] == "2026-11-01"
    assert saved["parishes"]["failed"]["bulletin_date"] is None

    untouched = tmp_path / "none.json"
    untouched.write_text(
        json.dumps(
            {
                "target_date": "2026-11-08",
                "parishes": {
                    "old": {
                        "outcome": "ok",
                        "bulletin_date": None,
                        "url": "https://parish.ie/09-11-08.pdf",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    before = untouched.read_text(encoding="utf-8")
    _pdf(bulletins / "old.pdf", [])
    none = apply_saved_dates(untouched, bulletins)
    assert none["dated"] == 0
    assert untouched.read_text(encoding="utf-8") == before


def test_filename_8th_november_kept_when_heading_has_no_date(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "8th-November-2026.pdf"
    _pdf(pdf, ["Parish notices"])
    url = "https://parish.ie/files/8th-November-2026.pdf"
    fields = _bulletin_date_fields(url, pdf_path=pdf, target=SUNDAY)
    assert fields["bulletin_date"] == "2026-11-08"
    assert fields["bulletin_date_uk"] == "08/11/2026"

    # The shared reader can return nothing. The in-week filename still stays.
    monkeypatch.setattr(
        "harvester.bulletin_freshness.heading_date_in_pdf",
        lambda path, target=None, url=None: None,
    )
    kept = _bulletin_date_fields(url, pdf_path=pdf, target=SUNDAY)
    assert kept["bulletin_date"] == "2026-11-08"

    named_only = tmp_path / "saved" / "8th-November-2026.pdf"
    named_only.parent.mkdir()
    _pdf(named_only, ["Parish notices"])
    from_name = _bulletin_date_fields(
        "https://parish.ie/current-newsletter/",
        pdf_path=named_only,
        target=SUNDAY,
    )
    assert from_name["bulletin_date"] == "2026-11-08"

    leftover = tmp_path / "cathedral.pdf"
    _pdf(leftover, ["Week beginning: 25th October 2026", "St Eunan's Cathedral Newsletter"])
    # Heading reader is mocked to None above, so this also checks the fallback.
    beat = _bulletin_date_fields(url, pdf_path=leftover, target=SUNDAY)
    assert beat["bulletin_date"] == "2026-11-08"
    assert beat["bulletin_date"] != "2026-10-25"


def test_last_sunday_front_page_stays_first_november_not_this_sunday(tmp_path: Path) -> None:
    pdf = tmp_path / "8th-November-2026.pdf"
    _pdf(pdf, ["FEAST OF ALL SAINTS 1st November 2026 Vol. 41. No.45"])
    url = "https://parish.ie/files/8th-November-2026.pdf"
    fields = _bulletin_date_fields(url, pdf_path=pdf, target=SUNDAY)
    assert fields["bulletin_date"] == "2026-11-01"
    assert fields["bulletin_date_uk"] == "01/11/2026"
    assert fields["bulletin_date"] != "2026-11-08"
    result = SimpleNamespace(
        key="probe-all-saints-not-a-parish",
        display_name="Probe",
        status="ok",
        url=url,
        file_path=pdf,
        file_type="pdf",
    )
    verdict = freshness_verdict_for_ok_result(result, SUNDAY)
    assert verdict.status == "stale"
    assert verdict.extracted_date == date(2026, 11, 1)
    assert verdict.extracted_date != SUNDAY


def test_no_filename_date_and_no_heading_stays_blank(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "current-newsletter.pdf"
    _pdf(pdf, ["Aifrinn na Seachtaine"])
    monkeypatch.setattr(
        "harvester.bulletin_freshness._ocr_first_page_text",
        lambda path: "",
    )
    fields = _bulletin_date_fields(
        "https://parish.ie/current-newsletter/",
        pdf_path=pdf,
        target=SUNDAY,
    )
    assert fields == {}
    assert fields.get("bulletin_date") != "2026-11-08"

    scan = tmp_path / "scan.pdf"
    _pdf(scan, [])
    monkeypatch.setattr(
        "harvester.bulletin_freshness._ocr_first_page_text",
        lambda path: "Sunday 8th November 2026",
    )
    ocr_fields = _bulletin_date_fields(
        "https://parish.ie/current-newsletter/",
        pdf_path=scan,
        target=SUNDAY,
    )
    assert ocr_fields["bulletin_date"] == "2026-11-08"
    monkeypatch.setattr(
        "harvester.bulletin_freshness._ocr_first_page_text",
        lambda path: "4 – 10 October 2026",
    )
    old_scan = _bulletin_date_fields(
        "https://parish.ie/current-newsletter/",
        pdf_path=scan,
        target=SUNDAY,
    )
    assert old_scan == {}
    assert old_scan.get("bulletin_date") != "2026-11-08"
