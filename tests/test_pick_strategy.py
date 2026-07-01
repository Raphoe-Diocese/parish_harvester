"""Tests for fast bulletin-link picking (Banagher / Pattern H)."""

from harvester.replay import _best_newsletter_link_index, _best_scored_link_index


def _entry(href: str, idx: int, text: str = "") -> dict:
    return {"href": href, "text": text, "idx": idx}


def test_best_newsletter_link_index_picks_highest_number() -> None:
    base = "https://www.banagherparish.com/information"
    entries = [
        _entry("/files/9/Newsletters/380/Bulletin-old", 0),
        _entry("/files/9/Newsletters/395/Bulletin-newest", 1),
        _entry("/files/9/Newsletters/384/Bulletin-mid", 2),
    ]
    assert _best_newsletter_link_index(entries, base, position="bottom") == 1


def test_best_newsletter_link_index_bottom_tiebreak() -> None:
    base = "https://www.banagherparish.com/information"
    entries = [
        _entry("/files/9/Newsletters/395/Bulletin-a", 0),
        _entry("/files/9/Newsletters/395/Bulletin-b", 5),
    ]
    assert _best_newsletter_link_index(entries, base, position="bottom") == 5


def test_best_scored_link_index_prefers_newer_slug_date() -> None:
    base = "https://example.org/bulletins/"
    entries = [
        _entry("/bulletins/14th-june-2026.pdf", 0),
        _entry("/bulletins/21st-june-2026.pdf", 1),
    ]
    assert _best_scored_link_index(entries, base, position="top") == 1
