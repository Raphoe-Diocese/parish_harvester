"""Regression for Carrigtwohill's published 15 November bulletin falsely rejected as 5 November."""
from __future__ import annotations

from datetime import date
from harvester.bulletin_freshness import extract_bulletin_date, check_bulletin_freshness

CURRENT = "https://carrigtwohillparish.ie/wp-content/uploads/2026/11/33rd-Sunday-15th-november.pdf"

def test_carrigtwohill_real_current_issue_url_is_15_november_not_5th():
    assert extract_bulletin_date(CURRENT) == date(2026,11,15)
    verdict = check_bulletin_freshness(CURRENT, date(2026,11,15))
    assert verdict.status == "fresh"
    assert verdict.extracted_date == date(2026,11,15)
