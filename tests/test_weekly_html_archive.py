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
