"""Regression tests for early, late and absent volunteer bulletin uploads.

A previous Sunday's paper must never be labelled as this Sunday's edition.
An early upload for the next Sunday can be accepted, but a missing date
must remain unknown rather than being invented from the harvest date.
"""
from datetime import date, timedelta

from harvester.bulletin_freshness import (
    check_bulletin_freshness,
    verdict_for_extracted_date,
)


def test_previous_sunday_is_stale():
    target = date(2026, 11, 22)
    result = verdict_for_extracted_date(target - timedelta(days=7), target)
    assert result.status == "stale"


def test_saturday_upload_for_sunday_is_fresh():
    target = date(2026, 11, 22)
    result = verdict_for_extracted_date(target - timedelta(days=1), target)
    assert result.status == "fresh"


def test_next_sunday_early_upload_is_fresh():
    target = date(2026, 11, 22)
    result = verdict_for_extracted_date(target + timedelta(days=7), target)
    assert result.status == "fresh"


def test_old_holiday_bulletin_remains_stale():
    target = date(2026, 11, 22)
    result = verdict_for_extracted_date(target - timedelta(days=35), target)
    assert result.status == "stale"


def test_undated_permanent_link_is_unknown():
    result = check_bulletin_freshness(
        "https://example.org/parish/newsletter.pdf", date(2026, 11, 22)
    )
    assert result.status == "unknown"
