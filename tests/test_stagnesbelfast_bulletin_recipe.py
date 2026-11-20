"""St Agnes Belfast publishes a genuine dated HTML weekly newsletter, not a PDF."""
from datetime import date
import json
from pathlib import Path

from harvester.replay import _newest_dated_post_url_from_listing


RECIPE_PATH = Path(__file__).resolve().parents[1] / "parishes/recipes/down_and_connor/stagnesbelfast.json"


def test_st_agnes_recipe_reenabled_for_html_bulletin():
    recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    assert recipe["parish_key"] == "stagnesbelfast"
    assert not recipe.get("skip", False)
    assert recipe.get("status") != "dead_url"
    assert recipe["site_type"] == "http_scrape_newest_html"
    assert recipe["playbook_type"] == "html_text_bulletin"
    assert recipe["start_url"] == "https://www.stagnesbelfast.com/"
    assert recipe["post_slug_patterns"] == ["st-agnes-parish-bulletin"]
    assert recipe["steps"][-1]["action"] == "print_to_pdf"
    assert recipe["steps"][-1]["skip_listing_nav"] is True
    assert "?p=6069" not in recipe["start_url"]


def test_st_agnes_picks_current_15_nov_post_not_prior_sunday():
    html = """
    <a href="/st-agnes-parish-bulletin-8th-november-2026/">old post</a>
    <a href="/st-agnes-parish-bulletin-15th-november-2026/">current post</a>
    <a href="/st-agnes-parish-bulletin-1st-november-2026/">older post</a>
    """
    picked = _newest_dated_post_url_from_listing(
        html,
        "https://www.stagnesbelfast.com/",
        ["st-agnes-parish-bulletin"],
        date(2026, 11, 15),
    )
    assert picked == "https://www.stagnesbelfast.com/st-agnes-parish-bulletin-15th-november-2026/"


def test_st_agnes_picks_22_nov_when_published_without_manual_repin():
    html = """
    <a href="/st-agnes-parish-bulletin-15th-november-2026/">last week</a>
    <a href="/st-agnes-parish-bulletin-22nd-november-2026/">this week</a>
    """
    picked = _newest_dated_post_url_from_listing(
        html,
        "https://www.stagnesbelfast.com/",
        ["st-agnes-parish-bulletin"],
        date(2026, 11, 22),
    )
    assert picked == "https://www.stagnesbelfast.com/st-agnes-parish-bulletin-22nd-november-2026/"
