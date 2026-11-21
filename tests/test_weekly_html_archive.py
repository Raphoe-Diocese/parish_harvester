from datetime import date

import fitz

from harvester.weekly_html_archive import write_weekly_html_issue


def test_prints_only_the_requested_sunday(tmp_path):
    html = """<h1>Sunday, 22nd November 2026</h1><h1>Community notices</h1>
    <p>Féile in Rantogue</p><h1>Sunday, 15th November 2026</h1><p>Previous sale</p>"""
    file = tmp_path / "issue.pdf"
    assert write_weekly_html_issue(html, date(2026, 11, 22), file)
    with fitz.open(file) as doc:
        text = "".join(page.get_text() for page in doc)
    assert "Féile in Rantogue" in text
    assert "Previous sale" not in text
    assert not write_weekly_html_issue(html, date(2026, 11, 29), tmp_path / "missing.pdf")


def test_weekly_issue_date_survives_an_unreadable_font_map(tmp_path, monkeypatch):
    from PyPDF2._page import PageObject
    from harvester.bulletin_freshness import heading_date_in_pdf_bytes
    from harvester.fetcher import extract_pdf_bulletin_date

    def unreadable(*args, **kwargs):
        raise ValueError("unsupported font map")

    monkeypatch.setattr(PageObject, "extract_text", unreadable)
    target = date(2026, 11, 22)
    file = tmp_path / "sample.pdf"
    html = "<h1>Sunday, 22nd November 2026</h1><p>Newsletter</p><h1>Sunday, 15th November 2026</h1>"
    assert write_weekly_html_issue(html, target, file)
    assert extract_pdf_bulletin_date(file) == target
    assert heading_date_in_pdf_bytes(file.read_bytes(), target=target) == target
