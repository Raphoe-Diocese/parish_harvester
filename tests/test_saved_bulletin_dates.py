"""Blank saved bulletins get a date only when one of the real ways finds it."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from reportlab.pdfgen import canvas

from harvester.bulletin_freshness import (
    extract_bulletin_date,
    extract_bulletin_date_from_text,
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


def test_blank_pdf_keeps_an_in_week_filename_and_not_09_11_08(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    _pdf(pdf, [])
    fields = _bulletin_date_fields(
        "https://parish.ie/files/Newsletter-8th-November-2026.pdf",
        pdf_path=pdf,
        target=SUNDAY,
    )
    assert fields["bulletin_date"] == "2026-11-08"
    assert fields["bulletin_date_uk"] == "08/11/2026"
    old = _bulletin_date_fields(
        "https://parish.ie/09-11-08.pdf",
        pdf_path=pdf,
        target=SUNDAY,
    )
    assert old.get("bulletin_date") != "2026-11-08"
    assert old.get("bulletin_date_uk") != "08/11/2026"
    undated = _bulletin_date_fields(
        "https://parish.ie/files/bulletin.pdf",
        pdf_path=pdf,
        target=SUNDAY,
    )
    assert undated == {}


def test_in_week_url_is_kept_when_pdf_heading_is_empty(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "bulletin.pdf"
    _pdf(pdf, [])
    monkeypatch.setattr(
        "harvester.bulletin_freshness.heading_date_in_pdf",
        lambda path, target=None, url=None: None,
    )
    fields = _bulletin_date_fields(
        "https://parish.ie/files/Newsletter-8th-November-2026.pdf",
        pdf_path=pdf,
        target=SUNDAY,
    )
    assert fields["bulletin_date"] == "2026-11-08"
    assert fields["bulletin_date_uk"] == "08/11/2026"


def test_october_front_page_this_week_url_uses_leftover_filename_win() -> None:
    found, way = issue_date_from_pages(
        ["week beginning 25 October 2026"],
        SUNDAY,
        url="https://parish.ie/files/Newsletter-8th-November-2026.pdf",
    )
    assert found == SUNDAY
    assert way == "url"
    outside, outside_way = issue_date_from_pages(
        ["4 – 10 October 2026"],
        SUNDAY,
        url="https://parish.ie/files/Newsletter-8th-November-2026.pdf",
    )
    assert outside == SUNDAY
    assert outside_way == "url"


def test_all_saints_front_page_this_week_url_stays_out() -> None:
    found, way = issue_date_from_pages(
        ["FEAST OF ALL SAINTS 1st November 2026"],
        SUNDAY,
        url="https://parish.ie/files/Newsletter-8th-November-2026.pdf",
    )
    assert found is None
    assert found != SUNDAY
    assert way == "front_outside"


def test_irish_in_week_date_is_this_sunday() -> None:
    found, way = issue_date_from_pages(["8 Samhain 2026"], SUNDAY)
    assert found == SUNDAY
    assert way == "front_page"
    ordinal, ordinal_way = issue_date_from_pages(["1ú Samhain 2026"], SUNDAY)
    assert ordinal is None
    assert ordinal != SUNDAY
    assert ordinal_way == "front_outside"
    assert extract_bulletin_date_from_text("8 Samhain 2026") == SUNDAY
    assert extract_bulletin_date_from_text("1ú Samhain 2026") == date(2026, 11, 1)


def test_irish_outside_week_is_not_this_sunday() -> None:
    found, way = issue_date_from_pages(["25 Deireadh Fómhair 2026"], SUNDAY)
    assert found is None
    assert found != SUNDAY
    assert way == "front_outside"


def test_irish_death_line_is_not_the_issue_date() -> None:
    found, way = issue_date_from_pages(
        ["Fuair Seán Ó Néill bás 8 Samhain 2026."],
        SUNDAY,
    )
    assert found is None
    assert way == ""
    assert extract_bulletin_date_from_text(
        "Fuair Seán Ó Néill bás 8 Samhain 2026."
    ) is None
    english, english_way = issue_date_from_pages(
        ["Mary died on 8th November 2026."],
        SUNDAY,
    )
    assert english is None
    assert english_way == ""


def test_blank_pdf_never_invents_harvest_sunday(tmp_path: Path) -> None:
    pdf = tmp_path / "photo.pdf"
    _pdf(pdf, [])
    found, way = saved_bulletin_issue_date(
        pdf, target=SUNDAY, url="https://parish.ie/files/newsletter.pdf"
    )
    assert found is None
    assert way == ""
    assert heading_date_in_pdf(
        pdf, target=SUNDAY, url="https://parish.ie/files/bulletin.pdf"
    ) is None


def test_script_reads_a_pdf_from_current(tmp_path: Path) -> None:
    bulletins = tmp_path / "Bulletins"
    current = bulletins / "current"
    current.mkdir(parents=True)
    _pdf(current / "words.pdf", ["Notices"], ["Sunday 8th November 2026"])
    path = tmp_path / "parish_status.json"
    path.write_text(
        json.dumps(
            {
                "target_date": "2026-11-08",
                "parishes": {
                    "words": {
                        "outcome": "ok",
                        "bulletin_date": None,
                        "url": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    summary = apply_saved_dates(path, bulletins)
    assert summary["dated"] == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["parishes"]["words"]["bulletin_date"] == "2026-11-08"
    assert saved["parishes"]["words"]["bulletin_date_uk"] == "08/11/2026"


def test_script_fills_report_downloaded_rows(tmp_path: Path) -> None:
    bulletins = tmp_path / "Bulletins"
    bulletins.mkdir()
    _pdf(bulletins / "words.pdf", ["Notices"], ["Sunday 8th November 2026"])
    _pdf(bulletins / "old.pdf", [])
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "target_date": "2026-11-08",
                "downloaded": [
                    {
                        "parish": "words",
                        "url": "",
                        "bulletin_date": None,
                    },
                    {
                        "parish": "old",
                        "url": "https://parish.ie/09-11-08.pdf",
                        "bulletin_date": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    status = tmp_path / "parish_status.json"
    status.write_text(
        json.dumps({"target_date": "2026-11-08", "parishes": {}}),
        encoding="utf-8",
    )
    summary = apply_saved_dates(status, bulletins, report_path=report_path)
    assert summary["dated"] == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["downloaded"][0]["bulletin_date"] == "2026-11-08"
    assert report["downloaded"][0]["bulletin_date_uk"] == "08/11/2026"
    assert report["downloaded"][1]["bulletin_date"] is None
