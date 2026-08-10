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


def test_best_newsletter_link_index_portglenone_bulletins_folder() -> None:
    base = "https://stmarysportglenone.org/?page_id=40"
    entries = [
        _entry("/download/9/Bulletins/106/15th-Sunday-in-Year-A", 0),
        _entry("/download/9/Bulletins/109/17th-SUNDAY-IN-ORDINARY-TIME", 1),
        _entry("/download/9/Bulletins/108/16TH-SUNDAY-IN-ORDINARY-TIME", 2),
    ]
    assert _best_newsletter_link_index(entries, base, position="top") == 1


def test_best_scored_link_index_prefers_newer_slug_date() -> None:
    base = "https://example.org/bulletins/"
    entries = [
        _entry("/bulletins/14th-june-2026.pdf", 0),
        _entry("/bulletins/21st-june-2026.pdf", 1),
    ]
    assert _best_scored_link_index(entries, base, position="top") == 1


def test_best_scored_link_index_ignores_garbled_future_year_filename() -> None:
    # kincasslagh.ie's old archive has typo'd filenames like "22107018.pdf"
    # (missing a digit) which parse under DDMMYYYY as day=22/month=10/
    # year=7018 — a constructible-but-absurd date() that used to silently
    # outrank the real, current 2026 bulletin (found 2026-08-10).
    base = "https://kincasslagh.ie/app/uploads/"
    entries = [
        _entry("/app/uploads/2021/07/22107018.pdf", 0, "18th July 2021"),
        _entry("/app/uploads/2026/07/20260705.pdf", 1, "5th July 2026"),
    ]
    assert _best_scored_link_index(entries, base, position="top") == 1


def test_best_scored_link_index_ignores_garbled_future_year_in_label_text() -> None:
    # Same site's listing also mislabels some rows with a nonsense far-future
    # year in the link *text* itself (e.g. "13th August 2107"), which the
    # slug-date parser used to accept just as readily as a real filename date.
    base = "https://kincasslagh.ie/app/uploads/"
    entries = [
        _entry("/app/uploads/2017/08/2170813.pdf", 0, "13th August 2107"),
        _entry("/app/uploads/2026/07/20260705.pdf", 1, "5th July 2026"),
    ]
    assert _best_scored_link_index(entries, base, position="top") == 1
