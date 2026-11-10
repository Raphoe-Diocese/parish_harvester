"""Pasted-site scanner asks the brain for parishes still missing 08/11/2026."""
from __future__ import annotations

from datetime import date

from harvester.bulletin_freshness import extract_bulletin_date
from harvester.recipe_brain import candidate_probe_urls
from scripts.scan_pasted_sites import (
    TARGET,
    _keep_probe,
    _one,
    brain_probe_urls,
    rows_to_probe,
)


def test_missing_parish_gets_brain_probe_urls_and_saved_sunday_is_skipped(monkeypatch):
    rows = [
        {"key": "missingparish", "url": "https://missingparish.ie/"},
        {"key": "savedparish", "url": "https://savedparish.ie/newsletter"},
        {"key": "alreadyhit", "url": "https://alreadyhit.ie/"},
        {"key": "olderok", "url": "https://olderok.ie/"},
        {"key": "facebookparish", "url": "https://www.facebook.com/someparish/"},
    ]
    parishes = {
        "missingparish": {"outcome": "failed", "bulletin_date": None},
        "savedparish": {"outcome": "ok", "bulletin_date": "2026-11-08"},
        "alreadyhit": {"outcome": "failed", "bulletin_date": None},
        "olderok": {"outcome": "ok", "bulletin_date": "2026-11-01"},
        "facebookparish": {"outcome": "failed"},
    }
    todo = rows_to_probe(rows, parishes, {"alreadyhit"})
    assert [row["key"] for row in todo] == ["missingparish", "olderok"]

    seen: list[str] = []

    def fake_prove(url, _accepted):
        seen.append(url)
        return None

    monkeypatch.setattr(
        "scripts.scan_pasted_sites._extra_urls",
        lambda _url: [
            "https://missingparish.ie/_files/ugd/abc123def456.pdf",
            "https://missingparish.ie/09-11-08.pdf",
            "https://missingparish.ie/11.08.26.pdf",
            "https://www.facebook.com/missingparish/newsletter.pdf",
            "https://missingparish.ie/Newsletter-8th-November-2026.pdf",
        ],
    )
    monkeypatch.setattr("scripts.scan_pasted_sites.prove_this_week_file", fake_prove)
    _one(todo[0], {TARGET})

    expected = [
        url
        for url, _site, _pattern in candidate_probe_urls("https://missingparish.ie/")
        if _keep_probe(url)
    ]
    assert expected
    assert set(brain_probe_urls("https://missingparish.ie/")) == set(expected)
    for url in expected:
        assert url in seen
    assert any("/current-newsletter/" in url for url in seen)
    assert any("wp-json" in url for url in seen)
    assert any("/wp-content/uploads/2026/11/" in url for url in seen)
    assert any(url.endswith("/pdf/081126.pdf") for url in seen)
    assert "https://missingparish.ie/Newsletter-8th-November-2026.pdf" in seen
    assert "https://missingparish.ie/09-11-08.pdf" not in seen
    assert "https://missingparish.ie/11.08.26.pdf" not in seen
    assert "savedparish" not in {row["key"] for row in todo}
    assert all("facebook.com" not in url.lower() for url in seen)
    assert all("/_files/ugd/" not in url.lower() for url in seen)
    for url in seen:
        named = extract_bulletin_date(url)
        assert named is None or named == date(2026, 11, 8)
    assert extract_bulletin_date("https://parish.ie/09-11-08.pdf") == date(2009, 11, 8)
    assert extract_bulletin_date("https://parish.ie/11.08.26.pdf") == date(2026, 8, 11)
    assert _keep_probe("https://parish.ie/09-11-08.pdf") is False
    assert _keep_probe("https://parish.ie/11.08.26.pdf") is False
    assert _keep_probe("https://parish.ie/_files/ugd/abc123def456.pdf") is False
    assert _keep_probe("https://static.wixstatic.com/media/abc123~mv2.pdf") is False
