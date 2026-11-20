"""Regression for official Gurranabraher weekly newsletter archive."""
from datetime import date
from harvester.replay import _score_http_scrape_pdf_hrefs
from harvester.newsletter_brain import same_sunday_urls

NOV8 = "https://www.gurranabraherparish.ie/wp-content/uploads/2026/11/Gurranabraher-32nd-Ordinary-Time-Nov-8th-2026-A.pdf"
NOV15 = "https://www.gurranabraherparish.ie/wp-content/uploads/2026/11/33rd-Ordinary-Time-Nov-15th-2026-A.pdf"
NOV22 = "https://www.gurranabraherparish.ie/wp-content/uploads/2026/11/Gurranabraher-Jesus-Christ-Universal-King-Nov-22nd-2026-A.pdf"


def test_22_nov_pdf_wins_even_when_anchor_caption_says_15_nov():
    scored = _score_http_scrape_pdf_hrefs(
        [NOV8, NOV15, NOV22],
        date(2026, 11, 22),
        labels={NOV22: "Click here to download the 15th November 2026 newsletter"},
    )
    assert same_sunday_urls(scored, date(2026, 11, 22)) == [NOV22]


def test_15_nov_pdf_still_selected_for_15_nov_target():
    scored = _score_http_scrape_pdf_hrefs([NOV8, NOV15],date(2026,11,15))
    assert same_sunday_urls(scored,date(2026,11,15)) == [NOV15]
